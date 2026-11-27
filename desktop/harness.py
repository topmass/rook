"""The main agent's harness: how Rook starts the agent, writes to it, and reads from it.

Claude Code is the default harness. A second harness subclasses Harness, implements its abstract methods, and adds one
entry in HARNESSES. It takes (model, effort), each None for its own default, and keeps them as .model and .effort.
It also has ready(): None when the agent can start, or a short reason it cannot, such as "agy is not installed".

Rook's reader (Companion.read_stream and read_agent in rook.py, with watch.delegation) reads Claude Code's
stream-json messages. Claude.read passes them through untouched. Another harness's read must yield the dicts
below, and Rook reads nothing else. A key marked "required" is read with [] and must be there.

| Message | Keys Rook reads | What Rook does |
|---|---|---|
| {"type": "system", "subtype": "init"} | mcp_servers: [{name, status}] | The status of the server named "t3", such as "connected" or "needs-auth", becomes t3_status. The startup turn says when T3 needs a sign-in. |
| {"type": "result"} | user_message_uuids (a list), or user_message_uuid (one id or None); result (the final text) or errors (a list of strings); terminal_reason or subtype; is_error | Ends the turns it lists. A result that lists no turn ends the only pending one. The first result after a launch ends the warm-up. A good turn says "completed" (or "success"), or the next restart's replay forgets it. is_error shows the text as an error. |
| {"type": "stream_event", "parent_tool_use_id": None, "event": {"type": "content_block_start", "content_block": {...}}} | content_block (required): type ("text", "tool_use" or other), name | A text block starts speech. Any other block ends it. A tool_use shows the activity name.split("__")[-1], except ToolSearch, Bash and mcp__t3__t3_pending_request. |
| ... "event": {"type": "content_block_delta", "delta": {...}} | delta (required): type "text_delta", text | Adds text. A blank line speaks the first paragraph as the answer. |
| ... "event": {"type": "content_block_stop"} | none | Speaks the text block, if it has text. Text before a tool call must be its own block. |
| {"type": "assistant", "parent_tool_use_id": None, "message": {"content": [...]}} | message.content (required): tool_use blocks with name, id, input | Logs each tool name. A top-level Bash shows a form from input.command and input.run_in_background. mcp__t3__t3_pending_request shows t3_pending_request for action respond and t3_thread_read for list or read. mcp__t3__t3_thread_send, mcp__t3__t3_thread_launch, and Bash with "t3 thread" in its command are kept by id until their result. |
| {"type": "user", "message": {"content": [...]}} | tool_result blocks: tool_use_id, content (a string or a list of {"type": "text", "text"}), is_error | A kept call's result goes to watch.delegation, which adds the thread to the watch list. |
| {"type": "control_request", "request_id", "request": {...}} | request (required): subtype "can_use_tool", tool_name (required), input; input.questions for AskUserQuestion | Shows the permission card. The answer comes back through permit() with this whole message. |
| {"type": "control_cancel_request", "request_id"} | request_id | Drops the card of that ask. |
| {"type": "thought", "text"} | text | Optional opt-in live thought chunk (never answer text). Spoken only when `speak_thoughts` enables thought narration on an owner-initiated turn. |
| The end of the stream | | The agent closed: Rook ends its turns and starts a new agent at the next turn. |

Tool names must reach Rook as Claude names them: Bash (with input.command and input.run_in_background),
ToolSearch (shown as no activity), AskUserQuestion (the questions card), and mcp__<server>__<tool> for tools from
Rook's tool servers, such as mcp__t3__t3_thread_send. Other names show as the activity name after the last "__".
"""
from abc import ABC, abstractmethod
import base64
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sys
from uuid import uuid4

import desk
import plugin_loader
import settings
OWNER = settings.OWNER_TOKEN  # The owner's name, filled in when the text leaves Rook.


def send(process, message):
    process.stdin.write((json.dumps(message) + "\n").encode())


def skill_sources(wow=False, plugin_skills=None):
    """Return skill source folders: skills/, plus wow/skills only when wow is active and present, then the
    skills folders of active bundled plugins. Their skills stand beside Rook's own, as rook:<name>."""
    root = Path(__file__).resolve().parent.parent
    sources = [root / "skills" if plugin_skills is None else Path(plugin_skills)]
    wow_skills = root / "wow/skills"
    if wow and (wow_skills / "wow/SKILL.md").is_file():
        sources.append(wow_skills)
    sources.extend(Path(folder) for folder in plugin_loader.skill_dirs()[0])
    return tuple(sources)


def plugin_user_skills():
    """Return the skills folders of active user plugins. Their skills join the user's own, as rook-user:<name>."""
    return tuple(Path(folder) for folder in plugin_loader.skill_dirs()[1])


def _has_skill(name):
    """Return whether a built-in or optional plugin skill exists in this checkout."""
    return any((folder / name / "SKILL.md").is_file() for folder in skill_sources(wow=True))


def rook_skills_dir():
    """Return Rook's own skills folder, honoring XDG_CONFIG_HOME."""
    return desk.config_dir() / "rook/skills"


def claude_config_dir():
    """Return Claude Code's user config folder, honoring CLAUDE_CONFIG_DIR."""
    return plugin_loader.host_skill_dirs()["claude"].parent


def claude_runtime_dir():
    """Return Rook's private runtime folder for generated Claude Code files."""
    return desk.runtime_dir() / "rook-claude"


def claude_settings_data(claude_dir=None, host_skills=None):
    """Build per-session Claude Code settings that hide user skills except the active plugins' allowed host skills,
    disable user plugins, and allow the local relay on macOS and an explicitly configured Herdr socket."""
    claude_dir = claude_config_dir() if claude_dir is None else Path(claude_dir)
    allowed = frozenset(plugin_loader.host_skills_allow() if host_skills is None else host_skills)
    overrides, plugins = {}, {}
    user_skills = claude_dir / "skills"
    try:
        entries = sorted(user_skills.iterdir()) if user_skills.is_dir() else []
    except OSError:
        entries = []
    for entry in entries:
        if entry.name.startswith(".") or entry.name in allowed:
            continue
        skill_md = entry / "SKILL.md"
        manifest = entry / ".claude-plugin/plugin.json"
        try:
            is_skill = skill_md.is_file()
            is_plugin = manifest.is_file()
        except OSError:
            continue
        if is_skill:
            overrides[entry.name] = "off"
            try:
                found = re.search(r"(?m)^name:\s*(.+?)\s*$", skill_md.read_text(errors="replace")[:1024])
            except OSError:
                found = None
            if found:
                name = found.group(1).strip().strip("\"'")
                if name and name not in allowed:
                    overrides[name] = "off"
        if is_plugin:
            try:
                plugin_name = json.loads(manifest.read_text(errors="replace")).get("name")
            except (OSError, ValueError, AttributeError):
                plugin_name = None
            if isinstance(plugin_name, str) and plugin_name and plugin_name not in allowed:
                plugins[f"{plugin_name}@skills-dir"] = False
    user_settings = claude_dir / "settings.json"
    try:
        has_settings = user_settings.is_file()
    except OSError:
        has_settings = False
    if has_settings:
        try:
            enabled = json.loads(user_settings.read_text(errors="replace")).get("enabledPlugins") or {}
        except (OSError, ValueError, AttributeError):
            enabled = {}
        if isinstance(enabled, dict):
            for key in enabled:
                plugins[key] = False
    config = {"skillOverrides": overrides, "enabledPlugins": plugins, "syncClaudeAiSkills": False}
    sockets = [str(desk.rook_socket())] if desk.IS_MAC else []
    if os.environ.get("ROOK_ALLOW_HERDR_SOCKET") == "1":
        socket_path = Path(os.environ.get("HERDR_SOCKET_PATH", ""))
        if socket_path.is_absolute() and socket_path.is_socket() and str(socket_path) not in sockets:
            sockets.append(str(socket_path))
    if sockets:
        config["sandbox"] = {"network": {"allowUnixSockets": sockets}}
    return config


def write_claude_files(runtime_dir=None, claude_dir=None, skills_dir=None, plugin_skills=None, host_skills=None):
    """Write Rook's private Claude Code settings file and custom plugin folder. Return (settings_path, plugin_dir).
    With skills from user plugins, the folder's skills is a folder of links to each skill, the user's own first."""
    runtime = claude_runtime_dir() if runtime_dir is None else Path(runtime_dir)
    runtime.mkdir(mode=0o700, parents=True, exist_ok=True)
    settings_path = runtime / "settings.json"
    temp = settings_path.with_suffix(".tmp")
    with os.fdopen(os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600), "w") as out:
        os.fchmod(out.fileno(), 0o600)
        json.dump(claude_settings_data(claude_dir, host_skills), out, indent=2)
    temp.replace(settings_path)
    skills = rook_skills_dir() if skills_dir is None else Path(skills_dir)
    extra = plugin_user_skills() if plugin_skills is None else tuple(Path(folder) for folder in plugin_skills)
    custom_plugin = None
    if skills.is_dir() or extra:
        custom_plugin = runtime / "plugin"
        manifest_dir = custom_plugin / ".claude-plugin"
        manifest_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        (manifest_dir / "plugin.json").write_text(json.dumps({
            "name": "rook-user",
            "version": "0.1.0",
            "description": "User skills for Rook.",
        }, indent=2) + "\n")
        link = custom_plugin / "skills"
        if link.is_symlink() or link.is_file():
            link.unlink()
        elif link.is_dir():
            shutil.rmtree(link)
        if not extra:
            link.symlink_to(skills)
            return settings_path, custom_plugin
        link.mkdir(mode=0o700)
        for folder in (skills, *extra):
            for entry in sorted(folder.iterdir()) if folder.is_dir() else ():
                if not entry.name.startswith(".") and (entry / "SKILL.md").is_file() and not (link / entry.name).exists():
                    (link / entry.name).symlink_to(entry)
    return settings_path, custom_plugin


def owned_plugin(plugin):
    """Rook's plugin as Claude Code reads it, with the owner tokens in its skills filled in. A copy Rook already made
    in its runtime folder (the --wow copy) is filled in place. Rook's own plugin is copied beside links to the rest of
    the repository, so each skill's relative paths, such as ${CLAUDE_PLUGIN_ROOT}/../desktop, still resolve."""
    source, runtime = Path(plugin), claude_runtime_dir()
    files = [file for file in sorted(source.rglob("*"))
             if file.is_file() and "__pycache__" not in file.relative_to(source).parts]
    if all(settings.render(file.read_text()) == file.read_text() for file in files if file.suffix == ".md"):
        return plugin
    try:
        if source.resolve().is_relative_to(runtime.resolve()):
            for file in files:
                if file.suffix == ".md":
                    file.write_text(settings.render(file.read_text()))
            return plugin
        return _write_owned_plugin(source, runtime / "rook-owned", files)
    except OSError as error:  # Rook still starts, with the skills as written.
        print(f"claude: owned_plugin failed ({type(error).__name__})", file=sys.stderr)
        return plugin


def _write_owned_plugin(source, target, files):
    shutil.rmtree(target, ignore_errors=True)
    target.mkdir(mode=0o700, parents=True)
    for entry in source.resolve().parent.iterdir():  # The repository's other folders, as links.
        if entry.name != source.name:
            (target / entry.name).symlink_to(entry)
    for file in files:
        out = target / source.name / file.relative_to(source)
        out.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if file.suffix == ".md":
            out.write_text(settings.render(file.read_text()))
        else:
            shutil.copyfile(file, out)
    return target / source.name


def _write_wow_plugin(plugin, runtime_dir=None, wow=True):
    """Build Rook's plugin in its runtime folder: plugin's manifest with skills/, plus wow/skills when --wow is
    active, and the skills of active bundled plugins, keeping rook:<name> as their names."""
    plugin = Path(plugin)
    sources = skill_sources(wow=wow)
    runtime = claude_runtime_dir() if runtime_dir is None else Path(runtime_dir)
    target = runtime / "rook-plugin"
    if target.exists():
        shutil.rmtree(target)
    (target / ".claude-plugin").mkdir(mode=0o700, parents=True)
    shutil.copyfile(plugin / ".claude-plugin/plugin.json", target / ".claude-plugin/plugin.json")
    for source in sources:
        for file in sorted(source.rglob("*")):
            rel = file.relative_to(source)
            if not file.is_file() or "__pycache__" in rel.parts:
                continue
            out = target / "skills" / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            if file.suffix == ".md":
                text = (file.read_text().replace("${CLAUDE_SKILL_DIR}", str(source / rel.parts[0]))
                        .replace("${CLAUDE_PLUGIN_ROOT}", str(plugin)))
                out.write_text(text)
            else:
                shutil.copy2(file, out)
    return target


class Harness(ABC):
    """Base interface for Rook's main agent harnesses.

    Subclasses set name, short, marks_tools_first, model, and effort, and implement the seven
    abstract methods below. A harness with its own setup wait limits may also define setup_quiet
    and setup_limit as class attributes; leave them unset to use Rook's SETUP_SECONDS.
    """

    name = ""  # Full name for error messages and startup lines.
    short = "Rook"  # Short name shown on permission cards.
    marks_tools_first = True  # True when the stream announces a tool before it can run.
    model = None  # Default model id when settings name none.
    effort = None  # Default effort level when settings name none.
    setup_problem = None  # One-sentence launch failure reason for Rook's fallback note.
    permission_mode = settings.PERMISSION_MODE  # The permission_mode setting, from pick(). See settings.PERMISSION_MODES.
    narrate_thoughts = False  # Opt-in: emit {"type": "thought", "text": ...} from live thought chunks.
    narrate_beats = False  # Opt-in: prompt allows brief spoken beats between later tool calls.
    heard = 0  # Monotonic timestamp of the last message received from the agent.

    def __init__(self, model=None, effort=None):
        self.model, self.effort = model or self.model, effort or self.effort

    def ready(self):
        """Return None when the agent can start, or one short sentence on why it cannot."""
        return None

    @abstractmethod
    def command(self, prompt, servers, session, plugin, denied):
        """Return the argv list to launch the agent process.

        servers maps Rook's MCP server names to their configs. denied lists T3 tools that must never run.
        """

    @abstractmethod
    def setup(self, start, later, wow):
        """Return the text for the initial setup turn.

        start maps server names to eager tools, later lists on-demand hints, and wow enables the wow skill.
        """

    @abstractmethod
    def begin(self, process, session, uuid, text):
        """Start the session on process and send the setup turn with id uuid."""

    @abstractmethod
    def turn(self, process, session, uuid, text, shots, steer):
        """Send one user turn with JPEG byte payloads in shots. steer folds it into a running turn."""

    @abstractmethod
    def interrupt(self, process):
        """Cancel the running turn and any queued turns on process."""

    @abstractmethod
    def permit(self, process, ask, allowed, answers=None, reason=None):
        """Answer a permission or question control_request ask. answers holds AskUserQuestion choices. reason, for a
        decline, tells the agent why, where its protocol carries one."""

    @abstractmethod
    def read(self, messages):
        """Yield Rook's stream-json message dicts from the agent's parsed stdout stream."""


class Claude(Harness):
    name = "Claude Code"  # In "Claude Code closed" and other errors.
    short = "Claude"  # In the permission card: "Claude requests Bash."
    # Its stream names a tool before the tool can run, so a request with no tool mark ran no tool.
    marks_tools_first = True
    model, effort = "claude-opus-5-5", "medium"  # The defaults, when the settings name none.

    def command(self, prompt, servers, session, plugin, denied):
        """The argv. servers are Rook's MCP servers by name. denied are T3 tools that must never run."""
        t3 = "t3" in servers
        plugin_dir = plugin
        try:
            settings_path, custom_plugin = write_claude_files()
            plugin_dir = _write_wow_plugin(plugin, wow="wow" in servers)
        except OSError as exc:
            print(f"claude: write_claude_files failed ({type(exc).__name__})", file=sys.stderr)
            settings_path, custom_plugin = None, None
        return [
            "claude", "-p", "--model", self.model, "--effort", self.effort,
            # The overlay answers every permission request that the mode leaves.
            *self.permission_flags(), "--permission-prompt-tool", "stdio",
            # Agent starts subagents, which Rook must not use. The list is never empty, so the flag never swallows
            # the next argument.
            "--disallowedTools", "Agent", *(f"mcp__t3__{tool}" for tool in denied if t3),
            *(f"mcp__{spec['name']}__{tool}" for spec in plugin_loader.servers() if spec["name"] in servers
              for tool in spec["denied_tools"]),
            # The owner's own answer to a thread's question goes through unreviewed: the prompt says it is always theirs.
            *(["--allowedTools", "mcp__t3__t3_pending_request"] if t3 else []),
            "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
            "--include-partial-messages",
            "--append-system-prompt", prompt, "--session-id", session,
            # Rook's own skills, from skills/ (with rook:wow added only when --wow is active), naming the owner.
            "--plugin-dir", str(owned_plugin(plugin_dir)),
            # The owner's custom skills live in ~/.config/rook/skills and load as rook-user:<name>.
            *(["--plugin-dir", str(custom_plugin)] if custom_plugin else []),
            # Hide user coding skills and plugins while keeping user hooks such as DCG.
            *(["--settings", str(settings_path)] if settings_path else []),
            # Claude Code would otherwise keep every screenshot in its session history.
            "--no-session-persistence", *(["--mcp-config", json.dumps({"mcpServers": servers})] if servers else []),
        ]

    def permission_flags(self):
        """The --permission-mode flag for permission_mode. rook is what Rook forced before: auto, whose classifier
        reviews risky actions. inherit sends no flag, so the person's own Claude Code settings decide."""
        mode = {"careful": "default", "automatic": "auto", "full": "bypassPermissions", "rook": "auto"}.get(
            self.permission_mode)
        return ["--permission-mode", mode] if mode else []

    def setup(self, start, later, wow=False):
        """The setup turn's text. start maps a server to the tools to load now. later names what to find on first
        use. wow enables loading the optional rook:wow skill when installed."""
        # Claude Code loads MCP tool schemas and skills on first use. A loaded schema stays in the context, so
        # load now only what most sessions use.
        start = [f"mcp__{server}__{tool}" for server, tools in start.items() for tool in tools]
        load_wow = "load the rook:wow skill, " if wow and _has_skill("wow") else ""
        return settings.render(f"Setup, not a request from {OWNER}: " + (f"call ToolSearch with select:{','.join(start)}, " if start else "")
                + load_wow + "then reply ready."
                + (f" Find these with ToolSearch when you first need one: {'; '.join(later)}." if later else "")
                + " When a tool you used before is missing, search for it again.")

    def begin(self, process, session, uuid, text):
        """Send the setup turn. The first result on this process belongs to it."""
        send(process, {"type": "user", "session_id": session, "parent_tool_use_id": None,
                       "uuid": uuid, "message": {"role": "user", "content": text}})

    def turn(self, process, session, uuid, text, shots, steer):
        """Send one turn: JPEG images, then the text. steer folds it into the running turn."""
        content = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                "data": base64.b64encode(shot).decode()}}
                   for shot in shots] + [{"type": "text", "text": text}]
        send(process, {"type": "user", "session_id": session, "parent_tool_use_id": None,
                       "uuid": uuid, "origin": {"kind": "human"}, "priority": "now" if steer else "next",
                       "message": {"role": "user", "content": content}})

    def interrupt(self, process):
        """Cancel the running turn and any queued ones."""
        send(process, {"type": "control_request", "request_id": str(uuid4()),
                       "request": {"subtype": "interrupt", "cancel_queued": True}})

    def permit(self, process, ask, allowed, answers=None, reason=None):
        """Answer a permission ask, the control_request message. answers are AskUserQuestion's answers."""
        tool_input = ask["request"].get("input", {})
        if answers is not None:
            tool_input = {**tool_input, "answers": answers}
        decision = ({"behavior": "allow", "updatedInput": tool_input} if allowed else
                    {"behavior": "deny", "message": reason or "The user declined this request."})
        send(process, {"type": "control_response", "response": {
            "subtype": "success", "request_id": ask["request_id"], "response": decision}})

    def read(self, messages):
        """Rook's messages from the agent's parsed stdout. Claude's stream is the contract, so it passes through."""
        return messages


# Each agent by its name in the agent setting. A "module.Class" string loads only when that agent is chosen, and only
# from module.py beside this file, so a missing or broken harness cannot stop Rook, and no other module of that name
# loads. Never name one after a standard module: Python's own antigravity opens a browser.
HARNESSES = {"claude": Claude, "antigravity": "agy_harness.Antigravity", "codex": "codex_harness.Codex", "pi": "pi_harness.Pi"}


def pick(settings):
    """Return (harness, problem) for the agent that the settings choose. problem is None, or one sentence on why the
    chosen agent cannot run. Then the harness is Claude Code with its defaults."""
    name = settings.get("agent", "claude")
    try:
        chosen = HARNESSES[name]
        if isinstance(chosen, str):
            module, _, cls = chosen.rpartition(".")
            path = Path(__file__).with_name(f"{module}.py")
            if not path.is_file():
                raise FileNotFoundError(f"{path.name} is missing")
            spec = importlib.util.spec_from_file_location(module, path)
            loaded = importlib.util.module_from_spec(spec)
            sys.modules[module] = loaded  # Code that looks its own module up, such as a dataclass, finds it.
            spec.loader.exec_module(loaded)
            chosen = getattr(loaded, cls)
        chosen = chosen(settings.get("agent_model"), settings.get("agent_effort"))
        problem = chosen.ready() if name != "claude" else None
    except Exception as exc:  # A missing or broken harness.
        problem = f"its harness did not load ({exc!r})"
    if problem:
        chosen, problem = Claude(), f"{name.title()} could not start: {problem.rstrip('.')}."
    chosen.permission_mode = settings.get("permission_mode") or Harness.permission_mode
    return chosen, problem
