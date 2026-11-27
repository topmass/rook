"""Rook's main agent on Pi (`pi`), through its RPC mode (`pi --mode rpc`).

RPC mode is JSONL on stdio: commands go in, and responses and session events come out. This harness turns Pi's
events into the Claude Code stream-json shapes that harness.py lists, so Rook's reader, watcher and cards keep their
code.

Pi runs with --no-session and screenshots travel inline, so no session file is written. Pi itself saves an output
it cuts (a script's or a tool's) in full to a file of its own in the temporary folder, such as /tmp/pi-codemode-*.txt,
at mode 0600, and never removes it; Rook's private folder cleanup does not touch those files.
Pi has no flag for tool servers, so pi_extension.ts registers Rook's. Their tools keep Claude Code's names,
mcp__<server>__<tool>. Denied tools are hidden. The declared tool list is CORE, fixed before the first request and never
changed in a session, so a local server's prompt cache holds. Every other tool is called from Pi's own codemode
scripts (docs/codemode.md), loaded without its models global. Rook records each call a script makes as a direct call
of that tool; the script itself is not a tool to Rook, and a failed script is one failed record.

Pi runs self-contained: a private agent folder holds only links to the person's models.json, auth.json and
mcp-auth.json, plus Rook's own settings.json, and the flags keep out context files, project files and extensions.

Pi has no permission modes: it runs every tool without asking (Pi's docs/security.md). So Rook maps no mode and adds
no layer. An extension's confirm or select dialog becomes a Rook card.

Self-check: ~/.local/share/rook/venv/bin/python desktop/pi_harness.py --check-pi
"""
import base64
import json
import os
from pathlib import Path
import shlex
import shutil
import sys
import time

import codex_harness  # Its skill rendering, table edits and session start hook, with Pi's tables.
import desk
from harness import Harness, _has_skill, plugin_user_skills, rook_skills_dir, send
import plugin_loader
import settings

OWNER = settings.OWNER_TOKEN
EXTENSION = Path(__file__).with_name("pi_extension.ts")
NAMES = {"bash": "Bash", "read": "Read", "edit": "Edit", "write": "Write", "grep": "Grep", "find": "Glob",
         "ls": "LS"}  # Pi's own tools by Claude Code's names. MCP names match already.
T3_CORE = ("t3_thread_list", "t3_thread_read", "t3_thread_send", "t3_thread_launch", "t3_pending_request")
# The declared tools, with T3_CORE when T3 is on. Scripts call the render tools.
CORE = ("read", "bash", "edit", "write", "codemode")
CODEMODE = "codemode"
ABORTED = "MCP request aborted"  # Pi's whole result for a server call it cut off.
SERVER_NOTES = {"t3": "T3 Code: threads, projects and pull requests.", "render": "Rook's gold-dust diagrams on screen.",
                "wow": "World of Warcraft game data."}
PERSON_FILES = ("models.json", "auth.json", "mcp-auth.json")  # Linked, never copied, so sign-ins stay the person's.
# The person's settings that carry over: documented keys (Pi 1.6.1 docs/settings.md) that load nothing. A key that
# is not here, such as packages, extensions, skills or one a later Pi adds, is left behind.
CARRIED_KEYS = ("defaultProvider", "defaultModel", "defaultThinkingLevel", "modelThinkingLevels", "thinkingBudgets",
                "enabledModels", "hideThinkingBlock", "notices", "cacheWarming", "steeringMode", "followUpMode",
                "compaction", "branchSummary", "transport", "httpProxy", "httpIdleTimeoutMs", "websocketConnectTimeoutMs",
                "retry", "shellPath", "shellCommandPrefix", "images", "enableInstallTelemetry", "enableAnalytics",
                "warnings")
SKILLS = [
    ("delegate/SKILL.md", "find one with ToolSearch, such as `select:mcp__t3__t3_thread_list`.",
     "call one that is not in your list from a codemode script by that name."),
    ("delegate/SKILL.md", "when ToolSearch cannot find the tools", "when a codemode script cannot reach the tools"),
    ("delegate/references/t3-command.md", "when ToolSearch cannot find the T3 tools",
     "when a codemode script cannot reach the T3 tools"),
    ("delegate/references/t3-tools.md", "Rook's Claude session", "Rook's Pi session"),
    ("wow/SKILL.md", "Find one that is not loaded yet with ToolSearch.", "Call one from a codemode script by its name."),
]
PROMPT = [("a full Claude Code session", "a full Pi session")]
TOOLS_LINE = ("\n\nWhen one tool in your list fits, call it directly. Call any other tool from a codemode script as "
              "`await tools.<name>(args)`, with the name a skill gives; searchTools() finds one you do not know. Never "
              "assign to `tools`. Return only what you need, not whole results.")
CLAUDE_ONLY = ("${CLAUDE_", "ToolSearch")
NEEDS_ATTENTION = "MCP servers need attention:"  # Pi's one notice after startup about servers that failed.


def agent_dir():
    return Path(os.environ.get("PI_CODING_AGENT_DIR") or Path.home() / ".pi/agent").expanduser().resolve()


def default_model():
    """The model Pi starts with when Rook names none, from Pi's own settings, or None."""
    try:
        model = json.loads((agent_dir() / "settings.json").read_text()).get("defaultModel")
    except (OSError, ValueError, AttributeError):
        return None
    return model if isinstance(model, str) and model else None


def tool_use(call_id, name, args):
    """Claude Code's assistant message for one tool call, with Claude Code's tool name."""
    name = NAMES.get(name, name)
    args = args if isinstance(args, dict) else {}
    if name == "Bash":
        args = {**args, "run_in_background": False}
    return {"type": "assistant", "parent_tool_use_id": None, "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": call_id, "name": name, "input": args}]}}


def stream(kind, **fields):
    return {"type": "stream_event", "parent_tool_use_id": None, "event": {"type": kind, **fields}}


def pi_servers(servers, denied):
    """Rook's servers as Pi's mcpServers entries: no tool is declared on its own, and denied tools stay hidden. A fixed
    description keeps Pi's server list in the prompt the same from the first request."""
    hidden = {"t3": denied, **{spec["name"]: spec["denied_tools"] for spec in plugin_loader.servers()}}
    return {name: {**config, "exposure": "codemode", "description": SERVER_NOTES.get(name, f"Rook's {name} tools."),
                   "toolExposure": {tool: "hidden" for tool in hidden.get(name, ())}}
            for name, config in servers.items()}


def core(servers, denied):
    """The declared tools, in order."""
    return [*CORE[:-1], *(f"mcp__t3__{tool}" for tool in T3_CORE if "t3" in servers and tool not in denied), CODEMODE]


def person_settings():
    path = agent_dir() / "settings.json"
    try:
        own = json.loads(path.read_text())
    except OSError:
        return {}
    except ValueError:
        print(f"pi: {path} is not valid JSON, so Rook's Pi starts without the person's settings.", file=sys.stderr)
        return {}
    return own if isinstance(own, dict) else {}


def agent_home(target):
    """Rook's private Pi agent folder: links to the person's own files and Rook's settings.json, nothing else. The
    folder is Rook's alone, so it is made again at each launch: it holds only Rook's links and settings, and what
    Pi itself writes there for Rook's session, such as its model list cache."""
    person = agent_dir()
    shutil.rmtree(target, ignore_errors=True)  # Unlinks the links; their targets stay.
    target.mkdir(mode=0o700, parents=True)
    if person.is_dir():
        for name in PERSON_FILES:  # Linked even when missing: Pi then makes the file in the person's folder.
            (target / name).symlink_to(person / name)
    own = person_settings()
    keep = {key: value for key, value in own.items() if key in CARRIED_KEYS}
    # Pi's shell children, such as relay.py or a pi the model starts, get the person's own agent folder back.
    child = (f"export PI_CODING_AGENT_DIR={shlex.quote(str(person))}"
             if os.environ.get("PI_CODING_AGENT_DIR") else "unset PI_CODING_AGENT_DIR")
    own_prefix = own.get("shellCommandPrefix")
    keep["shellCommandPrefix"] = child + (f"\n{own_prefix}" if isinstance(own_prefix, str) and own_prefix else "")
    descriptor = os.open(target / "settings.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as file:
        json.dump(keep, file)
    return target


def model_unknown(model):
    """Whether this provider/model may come from an extension of the person's, which Rook's Pi does not load: they
    load extensions or packages, and the provider is not in their models.json. Pi's docs list no built-in provider
    names to rule out, so this is a "may". Nothing runs and nothing waits."""
    provider, _, name = model.partition("/")
    own = person_settings()
    try:
        listed = json.loads((agent_dir() / "models.json").read_text()).get("providers") or {}
    except (OSError, ValueError, AttributeError):
        listed = {}
    return bool(name and (own.get("extensions") or own.get("packages")) and provider not in listed)


def skill_dirs(target, wow):
    """Render Rook's skills into target, and return every skills folder Pi loads: Rook's, then the person's own
    Rook skills, the active plugins' user skills and the host skills they allow."""
    shutil.rmtree(target, ignore_errors=True)
    target.mkdir(mode=0o700, parents=True)
    codex_harness.render_skills(target, wow=wow, table=SKILLS, banned=CLAUDE_ONLY)
    folders = [target, *(folder for folder in (rook_skills_dir(), *plugin_user_skills()) if folder.is_dir())]
    for name in plugin_loader.host_skills_allow():
        folders.extend(next(([folder / name] for folder in plugin_loader.host_skill_dirs().values()
                             if (folder / name / "SKILL.md").is_file()), []))
    return folders


class Pi(Harness):
    name = short = "Pi"
    marks_tools_first = True  # toolcall_start streams before the tool runs.
    model = effort = None  # Pi's own defaults.
    setup_quiet, setup_limit = 45, 90  # A local model may load slowly.

    def __init__(self, model=None, effort=None):
        super().__init__(model, effort)
        self.chosen = model  # Only a model Rook's settings name goes on Pi's command line.
        self.model = model or default_model() or "default"

    def ready(self):
        return None if shutil.which("pi") else "pi is not installed. Install Pi, or ask Rook to use Claude Code."

    def command(self, prompt, servers, session, plugin, denied):
        folders = skill_dirs(desk.runtime_dir() / "rook-pi/skills", wow="wow" in servers)
        home = agent_home(desk.runtime_dir() / "rook-pi/agent")
        own = person_settings()
        model = self.chosen or (f"{own['defaultProvider']}/{own['defaultModel']}"
                                if own.get("defaultProvider") and own.get("defaultModel") else "")
        if model and model_unknown(model):
            print(f"pi: the model {model} may come from one of the person's Pi extensions, which Rook's Pi session "
                  "does not load. If Pi cannot find it, Rook falls back to another agent.", file=sys.stderr)
        prompt = codex_harness.edit(prompt, PROMPT, "Rook's system prompt") + TOOLS_LINE  # Rendered already in rook.py.
        tools = core(servers, denied)
        # mcp__* keeps every server tool callable and keeps Pi's resource tools out. Naming single MCP tools would
        # drop all the others. The extension declares the core ones itself.
        return ["env", f"PI_CODING_AGENT_DIR={home}", f"ROOK_PI_SERVERS={json.dumps(pi_servers(servers, denied))}",
                f"ROOK_PI_CORE={json.dumps(tools)}", f"BROWSER={desk.false_exe()}",
                "pi", "--mode", "rpc", "--no-session", "--no-context-files", "--no-approve", "--no-extensions",
                "-e", "builtin:mcp", "-e", str(EXTENSION), "--tools", ",".join([*CORE, "mcp__*"]), "--no-skills",
                *(arg for folder in folders for arg in ("--skill", str(folder))),
                *(["--model", self.chosen] if self.chosen else []), *(["--thinking", self.effort] if self.effort else []),
                "--append-system-prompt", prompt]

    def setup(self, start, later, wow):
        """Claude Code's setup turn, with nothing to load: the core tools are declared, and scripts reach the rest."""
        return settings.render(f"Setup, not a request from {OWNER}: "
                               + ("load the wow skill, " if wow and _has_skill("wow") else "") + "then reply ready.")

    def begin(self, process, session, uuid, text):
        """Send the setup turn, with the lines of the owner's session start hook, run in Pi's own folder, as Claude
        Code's hook adds them to its session. The hook takes about 20 ms."""
        cwd = desk.process_cwd(process.pid, getattr(self, "workspace", None))
        if lines := codex_harness.memory(cwd):  # The hook's lines are data, passed as they are.
            text += settings.render(f"\n\nSession start lines, from {OWNER}'s session start hook:\n") + lines
        self.process, self.setup_uuid, self.heard = process, uuid, time.monotonic()
        self.running, self.steered, self.queue = None, [], []
        self.asks, self.dropped, self.statuses, self.servers_told = {}, [], {}, False
        self.texting, self.answer, self.error = False, "", None
        self.start(uuid, text, [])

    def start(self, uuid, text, images):
        self.running = uuid
        send(self.process, {"id": uuid, "type": "prompt", "message": text, "images": images})

    def turn(self, process, session, uuid, text, shots, steer):
        images = [{"type": "image", "data": base64.b64encode(shot).decode(), "mimeType": "image/jpeg"} for shot in shots]
        if self.running is None:
            self.start(uuid, text, images)
        elif steer:
            self.steered.append(uuid)
            send(process, {"id": uuid, "type": "prompt", "message": text, "images": images, "streamingBehavior": "steer"})
        else:
            self.queue.append((uuid, text, images))

    def interrupt(self, process):
        self.queue.clear()
        for request_id in list(self.asks):
            self.dropped.append(request_id)
            send(process, {"type": "extension_ui_response", "id": self.asks.pop(request_id)[0], "cancelled": True})
        if self.running is not None:
            send(process, {"type": "abort"})

    def permit(self, process, ask, allowed, answers=None, reason=None):
        """Answer the extension dialog this card stands for. Pi's dialogs carry no reason."""
        entry = self.asks.pop(ask.get("request_id"), None)
        if entry is None:
            return
        self.heard = time.monotonic()
        dialog, method = entry
        value = next(iter((answers or {}).values()), None)
        value = (value[0] if value else None) if isinstance(value, list) else value
        reply = ({"cancelled": True} if not allowed or value is None else
                 {"confirmed": value == "Yes"} if method == "confirm" else {"value": str(value)})
        send(process, {"type": "extension_ui_response", "id": dialog, **reply})

    async def read(self, messages):
        async for event in messages:
            self.heard = time.monotonic()
            for message in self.handle(event):
                yield message

    def close_text(self):
        if self.texting:
            self.texting = False
            yield stream("content_block_stop")

    def handle(self, event):
        kind = event.get("type")
        if kind == "message_update":
            update = event.get("assistantMessageEvent") or {}
            step = update.get("type")
            if step == "text_delta" and update.get("delta"):
                if not self.texting:
                    self.texting = True
                    yield stream("content_block_start", content_block={"type": "text", "text": ""})
                yield stream("content_block_delta", delta={"type": "text_delta", "text": update["delta"]})
            elif step == "text_end":
                yield from self.close_text()
            elif step == "toolcall_start":
                yield from self.close_text()
                if update.get("toolName") != CODEMODE:  # A script is not a tool to Rook; each call it makes is.
                    yield stream("content_block_start", content_block={
                        "type": "tool_use", "id": update.get("id"), "name": NAMES.get(update.get("toolName"), update.get("toolName"))})
            elif step == "toolcall_end":
                call = update.get("toolCall") or {}
                if call.get("name") != CODEMODE:
                    yield tool_use(call.get("id"), call.get("name"), call.get("arguments"))
        elif kind == "message_end" and (event.get("message") or {}).get("role") == "assistant":
            message = event["message"]
            yield from self.close_text()
            self.answer = "".join(block.get("text", "") for block in message.get("content") or ()
                                  if isinstance(block, dict) and block.get("type") == "text")
            self.error = (message.get("errorMessage") or "Pi's model failed.") if message.get("stopReason") == "error" else None
        elif kind == "tool_execution_start" and event.get("parentToolCallId"):  # A call a codemode script makes.
            name = NAMES.get(event.get("toolName"), event.get("toolName"))
            yield stream("content_block_start", content_block={"type": "tool_use", "id": event.get("toolCallId"), "name": name})
            yield tool_use(event.get("toolCallId"), event.get("toolName"), event.get("args"))
        elif kind == "tool_execution_end" and (event.get("toolName") != CODEMODE or event.get("isError")):
            if event.get("toolName") == CODEMODE:  # A failed script: one failed record, so Rook sees the attempt failed.
                yield tool_use(event.get("toolCallId"), CODEMODE, {})
            content = [{"type": "text", "text": block["text"]} for block in (event.get("result") or {}).get("content") or ()
                       if isinstance(block, dict) and isinstance(block.get("text"), str)]
            if event.get("isError") and [block["text"] for block in content] == [ABORTED]:
                # Pi cut the call off (the script's deadline or a stop): a send may have landed, as after a timeout.
                content = [{"type": "text", "text": ABORTED + ": it timed out or was stopped before its answer came, "
                                                    "so it may have landed."}]
            yield {"type": "user", "parent_tool_use_id": None, "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": event.get("toolCallId"), "content": content,
                 "is_error": bool(event.get("isError"))}]}}
        elif kind == "agent_settled":
            yield from self.settled(event.get("aborted"))
        elif kind == "response" and event.get("command") == "prompt" and (
                not event.get("success") or (event.get("data") or {}).get("disposition") == "handled"):
            # No run started for this prompt, so no agent_settled comes for it.
            uuid, problem = event.get("id"), None if event.get("success") else f"Pi refused the request: {event.get('error')}"
            if uuid == self.running:
                self.error = problem
                yield from self.settled(False)
            elif uuid in self.steered:  # A steer alone: the running turn goes on.
                self.steered.remove(uuid)
                yield {"type": "result", "user_message_uuids": [uuid], "result": problem or "", "is_error": bool(problem),
                       "terminal_reason": "error" if problem else "completed", "errors": [problem] if problem else []}
        elif kind == "extension_ui_request":
            yield from self.dialog(event)
        elif kind == "extension_error":
            print(f"pi: extension error in {event.get('event')}: {event.get('error')}", file=sys.stderr)

    def dialog(self, event):
        method, message = event.get("method"), str(event.get("message") or "")
        if method == "notify" and message.startswith(NEEDS_ATTENTION):
            for line in message.splitlines()[1:]:
                server, _, state = line.strip().partition(": ")
                if state:  # Not the last line, "Run /mcp to fix."
                    self.statuses[server] = "needs-auth" if state.startswith("needs sign-in") else "failed"
        elif method in ("confirm", "select"):  # One question, as AskUserQuestion's card shows it.
            options = ["Yes", "No"] if method == "confirm" else [str(option) for option in event.get("options") or ()]
            question = " ".join(part for part in (event.get("title"), event.get("message")) if part) or "Choose one."
            self.asks[event.get("id")] = (event.get("id"), method)
            yield {"type": "control_request", "request_id": event.get("id"), "request": {
                "subtype": "can_use_tool", "tool_name": "AskUserQuestion", "input": {"questions": [{
                    "question": question, "header": "Pi", "multiSelect": False,
                    "options": [{"label": option, "description": ""} for option in options]}]}}}
        elif method in ("input", "editor"):  # Rook's cards hold no free text.
            send(self.process, {"type": "extension_ui_response", "id": event.get("id"), "cancelled": True})

    def settled(self, aborted):
        """End the running turn and every steer folded into it, then start the next queued turn."""
        yield from self.close_text()
        if not self.servers_told:  # Before the setup turn's result, as Claude Code's init message comes first.
            self.servers_told = True
            yield {"type": "system", "subtype": "init", "mcp_servers": [
                {"name": name, "status": status} for name, status in self.statuses.items()]}
        for request_id in self.dropped + list(self.asks):
            yield {"type": "control_cancel_request", "request_id": request_id}
        self.dropped, self.asks = [], {}
        uuids, problem, answer = [self.running, *self.steered], self.error, self.answer
        self.running, self.steered, self.answer, self.error = None, [], "", None
        if uuids[0] == self.setup_uuid and problem:  # Rook falls back to Claude Code with this sentence.
            self.setup_problem = f"Pi could not answer its setup turn: {problem[:200].rstrip('.')}."
            print(f"pi: {self.setup_problem}", file=sys.stderr)
            self.process.kill()
            return
        if uuids[0] is not None:
            yield {"type": "result", "user_message_uuids": uuids, "result": problem or answer, "is_error": bool(problem),
                   "terminal_reason": "error" if problem else "cancelled" if aborted else "completed",
                   "errors": [problem] if problem else []}
        if self.queue:
            self.start(*self.queue.pop(0))


def check():
    """The harness against a stand-in pi that speaks RPC mode, then the real pi against a stand-in model and tool
    server. No real model, window or sound."""
    import asyncio
    import harness
    import tempfile

    real_pi = shutil.which("pi")
    # 1. Skills, prompt and setup text: no Claude-only words, and Rook's tables still match.
    with tempfile.TemporaryDirectory(prefix="rook-pi-check-") as tmp:
        base = Path(tmp)
        # The private agent folder and every skills folder in scratch: never the running Rook's or the owner's.
        os.environ.update(XDG_RUNTIME_DIR=str(base / "run"), XDG_CONFIG_HOME=str(base / "config"), HOME=str(base / "home"))
        codex_harness.AGENTS = base / "no-agents"  # No session start hook: the owner's real one stays out.
        folders = skill_dirs(base / "skills", wow=True)
        assert folders[0] == base / "skills" and (base / "skills/delegate/SKILL.md").is_file()
        skill = (base / "skills/delegate/SKILL.md").read_text()
        assert "from a codemode script by that name" in skill and "tool_search" not in skill
        codex_harness.edit((codex_harness.ROOT / "desktop/rook.py").read_text(), PROMPT, "desktop/rook.py")
        text = Pi().setup({"t3": ("t3_thread_send", "t3_thread_read")}, ["the other T3 tools"], False)
        assert text.endswith("then reply ready.") and "tool_search" not in text and "ToolSearch" not in text, text
        servers = pi_servers({"t3": {"type": "http", "url": "http://127.0.0.1:1/mcp"}, "render": {"command": "uv"}},
                             ("t3_project_delete",))
        assert servers["t3"] == {"type": "http", "url": "http://127.0.0.1:1/mcp", "exposure": "codemode",
                                 "description": SERVER_NOTES["t3"], "toolExposure": {"t3_project_delete": "hidden"}}, servers
        assert servers["render"]["toolExposure"] == {}

        # 2. pick() and the argv, with a stand-in pi on PATH and Pi's settings in a scratch folder.
        (base / "bin").mkdir()
        standin = base / "bin/pi"
        standin.write_text(f"#!{sys.executable}\n" + STANDIN)
        standin.chmod(0o755)
        os.environ["PATH"] = f"{base / 'bin'}:{os.environ['PATH']}"
        os.environ["PI_CODING_AGENT_DIR"] = str(base / "agent")
        (base / "agent").mkdir()
        (base / "agent/settings.json").write_text(json.dumps({"defaultModel": "llamacpp", "extensions": ["x.ts"], "packages": ["y"],
                                                              "httpProxy": "http://proxy:1", "shellCommandPrefix": "set -o pipefail",
                                                              "futureLoader": ["z"]}))  # Unknown keys stay behind.
        for name in ("models.json", "auth.json", "AGENTS.md", "SYSTEM.md", "mcp.json"):  # No mcp-auth.json: no link.
            (base / "agent" / name).write_text("{}")
        chosen, problem = harness.pick({"agent": "pi"})
        assert type(chosen).__name__ == "Pi" and problem is None and chosen.model == "llamacpp", (chosen, problem)
        argv = chosen.command("You run as a full Claude Code session. Your memory is the agent memory folder that "
                              "your session start message names.", {"render": {"command": "uv"}}, "s", None, ())
        # Self-contained: the person's context files, project files, extensions, servers and skills stay out.
        at = argv.index("pi")
        assert argv[at:at + 13] == ["pi", "--mode", "rpc", "--no-session", "--no-context-files", "--no-approve",
                                    "--no-extensions", "-e", "builtin:mcp", "-e", str(EXTENSION), "--tools",
                                    ",".join([*CORE, "mcp__*"])], argv
        assert argv[at + 13] == "--no-skills" and "tool_search" not in argv[at + 12]
        assert not {"builtin:codemode", "builtin:tool-search"} & set(argv)  # Only Rook's extension loads code mode.
        home = base / "run/rook-pi/agent"
        assert f"PI_CODING_AGENT_DIR={home}" in argv and json.loads(argv[argv.index("env") + 3].partition("=")[2]) == list(CORE)
        assert sorted(path.name for path in home.iterdir()) == ["auth.json", "mcp-auth.json", "models.json", "settings.json"]
        assert all(os.readlink(home / name) == str(base / "agent" / name) for name in PERSON_FILES)
        assert (home / "settings.json").stat().st_mode & 0o777 == 0o600
        assert json.loads((home / "settings.json").read_text()) == {
            "defaultModel": "llamacpp", "httpProxy": "http://proxy:1",
            "shellCommandPrefix": "export PI_CODING_AGENT_DIR=" + shlex.quote(str(base / "agent")) + "\nset -o pipefail"}
        assert "--model" not in argv and "--thinking" not in argv and "a full Pi session" in argv[-1]
        assert argv[-1].endswith(TOOLS_LINE)
        assert core({"t3": {}}, ("t3_thread_launch",)) == ["read", "bash", "edit", "write", "mcp__t3__t3_thread_list",
                                                            "mcp__t3__t3_thread_read", "mcp__t3__t3_thread_send",
                                                            "mcp__t3__t3_pending_request", "codemode"]
        # The prompt comes rendered from rook.py, where the person's notes pass as they are: no second render here.
        argv = chosen.command("a full Claude Code session. Notes: ⟦owner⟧ likes tea.", {}, "s", None, ())
        assert argv[-1] == "a full Pi session. Notes: ⟦owner⟧ likes tea." + TOOLS_LINE, argv[-1]
        argv = Pi("server-pc/llamacpp", "high").command("a full Claude Code session, that your session start message "
                                                        "names", {}, "s", None, ())
        assert argv[argv.index("--model") + 1] == "server-pc/llamacpp" and argv[argv.index("--thinking") + 1] == "high"

        # 3. Turns against the stand-in: speech, a tool, a steer, a queued turn, a card, a stop, a failed setup.
        async def run(mode, steps):
            pi = Pi()
            process = await asyncio.create_subprocess_exec(
                str(standin), stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                env={**os.environ, "STANDIN_MODE": mode})
            pi.begin(process, "s", "setup", "Setup")
            out, reader = [], None

            async def collect():
                async def lines():
                    while line := await process.stdout.readline():
                        yield json.loads(line)
                async for message in pi.read(lines()):
                    out.append(message)
            reader = asyncio.create_task(collect())
            for step in steps:
                await asyncio.sleep(0.3)
                step(pi, process, out)
            await asyncio.sleep(0.5)
            process.stdin.close()
            await asyncio.wait_for(reader, 5)
            return pi, out

        def results(out):
            return [(m["user_message_uuids"], m["result"], m["terminal_reason"]) for m in out if m["type"] == "result"]

        def ask(pi, process, out):
            card = next(m for m in out if m["type"] == "control_request")
            question = card["request"]["input"]["questions"][0]
            assert [o["label"] for o in question["options"]] == ["Yes", "No"], question
            pi.permit(process, card, True, {question["question"]: "Yes"})

        pi, out = asyncio.run(run("normal", [
            lambda pi, process, out: pi.turn(process, "s", "t1", "hello", [b"jpeg"], False),
            lambda pi, process, out: pi.turn(process, "s", "t2", "and this", [], True),
            lambda pi, process, out: pi.turn(process, "s", "t3", "later", [], False),
            ask]))
        kinds = [m["type"] for m in out]
        assert kinds[0] == "stream_event" and "system" in kinds, kinds
        init = next(m for m in out if m["type"] == "system")
        assert init["mcp_servers"] == [{"name": "t3", "status": "needs-auth"}], init
        assert results(out) == [(["setup"], "ready", "completed"), (["t1", "t2"], "done: hello+and this", "completed"),
                                (["t3"], "confirmed: True", "completed")], results(out)
        tool = next(m for m in out if m["type"] == "assistant")["message"]["content"][0]
        assert tool["name"] == "Bash" and tool["input"] == {"command": "ls", "run_in_background": False}, tool
        spoken = "".join(m["event"]["delta"]["text"] for m in out
                         if m["type"] == "stream_event" and m["event"]["type"] == "content_block_delta")
        assert spoken.startswith("ready") and "done: hello+and this" in spoken, spoken

        pi, out = asyncio.run(run("slow", [
            lambda pi, process, out: pi.turn(process, "s", "t1", "long", [], False),
            lambda pi, process, out: pi.interrupt(process)]))
        assert results(out)[-1] == (["t1"], "", "cancelled"), results(out)

        pi, out = asyncio.run(run("broken", []))
        assert not results(out) and "No API key" in pi.setup_problem, (out, pi.setup_problem)

        # 4. The watcher and cards: a call a codemode script makes reaches Rook exactly as a direct call of that tool.
        send_args = {"threadId": "t", "message": "brief"}
        reply = {"content": [{"type": "text", "text": '{"messageId": "m1"}'}]}

        def seen(events):
            pi = Pi()
            pi.texting = False
            return [message for event in events for message in pi.handle(event)]

        def model_call(call_id, name, args):
            return [{"type": "message_update", "assistantMessageEvent": {"type": "toolcall_start", "id": call_id, "toolName": name}},
                    {"type": "message_update", "assistantMessageEvent": {"type": "toolcall_end", "toolCall": {
                        "type": "toolCall", "id": call_id, "name": name, "arguments": args}}}]

        def ran(call_id, name, args, result, error=False, parent=None):
            at = {"toolCallId": call_id, "toolName": name, **({"parentToolCallId": parent} if parent else {})}
            return [{"type": "tool_execution_start", **at, "args": args},
                    {"type": "tool_execution_end", **at, "result": result, "isError": error}]

        def script(inner, error=False):  # A codemode call whose script makes the inner calls, as [(name, args, result, error)].
            done = {"content": [{"type": "text", "text": "Script failed" if error else "Script completed"}]}
            nested = [event for n, (name, args, result, bad) in enumerate(inner, 1)
                      for event in ran(f"c1/{n}", name, args, result, bad, parent="c1")]
            return [*model_call("c1", CODEMODE, {"code": "..."}), {"type": "tool_execution_start", "toolCallId": "c1",
                                                                    "toolName": CODEMODE, "args": {"code": "..."}},
                    *nested, {"type": "tool_execution_end", "toolCallId": "c1", "toolName": CODEMODE, "result": done, "isError": error}]

        direct = seen([*model_call("c1/1", "mcp__t3__t3_thread_send", send_args),
                       *ran("c1/1", "mcp__t3__t3_thread_send", send_args, reply)[1:]])
        assert [m["type"] for m in direct] == ["stream_event", "assistant", "user"], direct
        assert seen(script([("mcp__t3__t3_thread_send", send_args, reply, False)])) == direct  # Recorded as a direct send.
        three = seen(script([("mcp__t3__t3_thread_read", {"threadId": "t"}, reply, False), ("bash", {"command": "ls"}, reply, False),
                             ("mcp__t3__t3_thread_send", send_args, reply, False)]))
        uses = [m["message"]["content"][0] for m in three if m["type"] == "assistant"]
        assert [u["name"] for u in uses] == ["mcp__t3__t3_thread_read", "Bash", "mcp__t3__t3_thread_send"], uses
        assert uses[1]["input"] == {"command": "ls", "run_in_background": False}
        assert sum(m["type"] == "user" for m in three) == 3
        assert seen(script([])) == []  # A script that only searches records nothing.
        failed = seen(script([], error=True))  # A failed script is one failed record.
        assert [m["type"] for m in failed] == ["assistant", "user"] and failed[1]["message"]["content"][0]["is_error"], failed
        cut = seen(script([("mcp__t3__t3_thread_send", send_args, {"content": [{"type": "text", "text": ABORTED}]}, True)], error=True))
        answer = next(m for m in cut if m["type"] == "user")["message"]["content"][0]
        assert answer["is_error"] and "timed out" in answer["content"][0]["text"], cut  # Rook reads it as unknown.
        # A turn that opens with a long script: Pi's first event for the call moves heard past the hand-off, so Rook's
        # first-output watchdog (silent_too_long in rook.py: heard <= handed) never counts the turn as silent.
        async def opens_with_script():
            pi, handed = Pi(), time.monotonic()
            pi.texting, pi.heard = False, handed

            async def events():
                for event in script([("mcp__t3__t3_thread_send", send_args, reply, False)])[:3]:
                    yield event
                await asyncio.sleep(0.3)  # The script runs past a short watchdog bound of 0.2 s.
                assert pi.heard > handed and time.monotonic() - handed >= 0.2
            return [message async for message in pi.read(events())]
        assert asyncio.run(opens_with_script()) == []  # And nothing of the script shows as a tool.
        bad = seen(script([("mcp__t3__t3_thread_send", send_args, reply, True)]))
        assert [m["message"]["content"][0]["is_error"] for m in bad if m["type"] == "user"] == [True]  # A failed inner call.

        # 5. The real pi with Rook's launch line, a stand-in model and a stand-in T3: the declared list is the same
        # at every request, through a search, an execute, a core call and a second prompt, and a late T3 never joins.
        if real_pi:
            real_check(real_pi, base)
        else:
            print("pi is not installed: skipped the real-pi part")
    print("all checks passed")


def real_check(real_pi, base):
    import http.server
    import subprocess
    import threading

    stub = base / "stub_t3.py"
    stub.write_text(STUB_T3)
    person, work = base / "person", base / "work/inner"
    os.environ["PI_CODING_AGENT_DIR"] = str(person)
    os.environ["PATH"] = os.pathsep.join(folder for folder in os.environ["PATH"].split(os.pathsep) if folder != str(base / "bin"))
    # The person's own setup, each piece with a marker: none of it may reach the model.
    for folder in (person / "extensions", person / "skills/marker", person / "prompts", work):
        folder.mkdir(parents=True)
    for folder in (person, base / "work"):
        (folder / "AGENTS.md").write_text("MARKER-AGENTS")
        (folder / "AGENTS.override.md").write_text("MARKER-OVERRIDE")
    (person / "SYSTEM.md").write_text("MARKER-SYSTEM")
    (person / "APPEND_SYSTEM.md").write_text("MARKER-APPEND")
    (person / "skills/marker/SKILL.md").write_text("---\nname: marker-skill\ndescription: MARKER-SKILL\n---\nMARKER-SKILL\n")
    (person / "prompts/marker.md").write_text("MARKER-PROMPT")
    marker = 'export default function (pi: any) { pi.registerTool({name: "marker_tool", label: "m", description: "MARKER-TOOL", ' \
             'parameters: {type: "object", properties: {}}, async execute() { return {content: [], details: {}}; }}); }'
    (person / "extensions/marker.ts").write_text(marker)
    (person / "settings.json").write_text(json.dumps({"extensions": [str(person / "extensions/marker.ts")]}))
    (person / "mcp.json").write_text(json.dumps({"mcpServers": {"marker": {"command": sys.executable, "args": [str(stub)]}}}))

    def session(script, prompts, delay, wait_ms):
        requests = []

        class Model(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                requests.append((json.dumps(body.get("tools")), body["messages"][-1], json.dumps(body)))
                kind, value = script[min(len(requests) - 1, len(script) - 1)]
                delta = ({"content": value} if kind == "text" else {"tool_calls": [{
                    "index": 0, "id": f"c{len(requests)}", "type": "function",
                    "function": {"name": kind, "arguments": json.dumps(value)}}]})
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                for choice in ({"index": 0, "delta": {"role": "assistant", **delta}},
                               {"index": 0, "delta": {}, "finish_reason": "stop" if kind == "text" else "tool_calls"}):
                    self.wfile.write(b"data: " + json.dumps({"id": "x", "object": "chat.completion.chunk",
                                                             "choices": [choice]}).encode() + b"\n\n")
                self.wfile.write(b"data: [DONE]\n\n")

        server = http.server.HTTPServer(("127.0.0.1", 0), Model)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        (base / "person/models.json").write_text(json.dumps({"providers": {"stand-in": {
            "baseUrl": f"http://127.0.0.1:{server.server_port}/v1", "api": "openai-completions", "apiKey": "x",
            "models": [{"id": "m"}]}}}))
        argv = Pi("stand-in/m").command("a full Claude Code session", {"t3": {"command": sys.executable, "args": [str(stub)]}},
                                        "s", None, ("t3_project_delete",))
        argv[argv.index("pi")] = real_pi
        env = {"PATH": os.environ["PATH"], "HOME": str(base / "home"), "XDG_CONFIG_HOME": str(base / "config"),
               "XDG_DATA_HOME": str(base / "data"), "XDG_STATE_HOME": str(base / "state"), "XDG_CACHE_HOME": str(base / "cache"),
               "XDG_RUNTIME_DIR": str(base / "run"), "PI_OFFLINE": "1", "STUB_DELAY": str(delay), "ROOK_PI_WAIT_MS": str(wait_ms),
               "ROOK_PI_SCRIPT_MS": "1500"}
        process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                   env=env, cwd=work)
        settled = threading.Semaphore(0)
        events = []

        def read():
            for line in process.stdout:
                events.append(json.loads(line))
                if events[-1].get("type") == "agent_settled":
                    settled.release()
        threading.Thread(target=read, daemon=True).start()
        for at, prompt in enumerate(prompts):
            process.stdin.write(json.dumps({"id": f"p{at}", "type": "prompt", "message": prompt}) + "\n")
            process.stdin.flush()
            assert settled.acquire(timeout=20), f"pi did not finish prompt {at}"
            time.sleep(delay if at == 0 else 0)
        process.stdin.close()
        errors = process.stderr.read()
        process.wait(10)
        server.shutdown()
        home = base / "run/rook-pi/agent"
        assert all((home / name).is_symlink() for name in PERSON_FILES), "Pi replaced a link to the person's file"
        return requests, errors, events

    def said(request):
        return json.dumps(request[1].get("content"))

    send = {"threadId": "t", "message": "brief"}

    def code(text):
        return ("codemode", {"code": text})

    requests, errors, events = session([
        ("text", "ready"), code('return await searchTools("project list")'),
        code("return await tools.mcp__t3__t3_project_list({})"), ("mcp__t3__t3_thread_send", send),
        ("bash", {"command": "echo CHILD=${PI_CODING_AGENT_DIR-unset}"}),
        code("return await tools.mcp__t3__t3_project_delete({})"), code("return typeof models"),
        code('// @options: {"timeout_ms": 600000}\nwhile (true) {}'),
        code('const a = await tools.mcp__t3__t3_thread_read({threadId: "t"}); '
             'const b = await tools.mcp__t3__t3_thread_send({threadId: "t", message: "brief"}); return [a, b].length'),
        ("text", "done")], ["Setup", "go", "and again"], 0, 10000)
    tools = {request[0] for request in requests}
    assert len(requests) == 11 and len(tools) == 1, (len(requests), len(tools), errors[-500:])
    names = [tool["function"]["name"] for tool in json.loads(tools.pop())]
    assert names == ["read", "bash", "edit", "write", "codemode", *(f"mcp__t3__{t}" for t in T3_CORE)], names  # As sent.
    first = requests[0][2]
    assert "MARKER" not in first and "marker" not in first, [m for m in first.split('"') if "MARKER" in m or "marker" in m][:5]
    assert "mcp__t3__t3_project_list" in said(requests[2]) and "t3_project_delete" not in said(requests[2]), said(requests[2])
    assert "t3_project_list ok" in said(requests[3]) and "t3_thread_send ok" in said(requests[4])
    assert f"CHILD={person}" in said(requests[5]), said(requests[5])  # Children get the person's own folder back.
    assert "Script failed" in said(requests[6]) and "t3_project_delete ok" not in said(requests[6]), said(requests[6])  # Denied.
    assert "undefined" in said(requests[7]), said(requests[7])  # No models global.
    assert "Script failed" in said(requests[8]), said(requests[8])  # Rook's deadline holds over the script's own.
    assert "2" in said(requests[9]), said(requests[9])
    assert "tool list changed" not in errors, errors[-500:]
    # Pi's real events through the harness: each call a script makes is one record under its own name, a search
    # records none, and a failed script is one failed record.
    pi = Pi()
    pi.texting, pi.process = False, None
    records = [m for event in events if event.get("type") != "agent_settled" for m in pi.handle(event)]
    uses = [m["message"]["content"][0] for m in records if m["type"] == "assistant"]
    results = {block["tool_use_id"]: block for m in records if m["type"] == "user" for block in m["message"]["content"]}
    assert [u["name"] for u in uses] == ["mcp__t3__t3_project_list", "mcp__t3__t3_thread_send", "Bash", CODEMODE, CODEMODE,
                                         "mcp__t3__t3_thread_read", "mcp__t3__t3_thread_send"], [u["name"] for u in uses]
    assert [results[u["id"]]["is_error"] for u in uses] == [False, False, False, True, True, False, False], uses
    assert uses[-1]["input"] == send and uses[0]["id"].endswith("/1")
    # A model whose provider only an extension of the person's could give.
    assert model_unknown("ghost/m") and not model_unknown("stand-in/m") and not model_unknown("ghost")

    # T3 answers after the wait: its core tools stay out of the list, and a script reaches them.
    requests, errors, _ = session([("text", "ready"), code(f"return await tools.mcp__t3__t3_thread_send({json.dumps(send)})"),
                                   ("text", "done")], ["Setup", "go"], 2, 300)
    tools = {request[0] for request in requests}
    assert len(requests) == 3 and len(tools) == 1 and "mcp__t3" not in tools.pop(), errors[-500:]
    assert "t3's tools were not ready" in errors and "t3_thread_send ok" in said(requests[2]), (errors[-500:], said(requests[2]))


# A stand-in T3 tool server on stdio: Rook's five core T3 tools, one more, and one denied. STUB_DELAY holds its start.
STUB_T3 = r'''
import json, os, sys, time
NAMES = ["t3_thread_list", "t3_thread_read", "t3_thread_send", "t3_thread_launch", "t3_pending_request",
         "t3_project_list", "t3_project_delete"]
TOOLS = [{"name": name, "description": f"The {name.replace('_', ' ')} tool.",
          "inputSchema": {"type": "object", "properties": {"threadId": {"type": "string"}}}} for name in NAMES]
for line in sys.stdin:
    message = json.loads(line)
    if message.get("id") is None:
        continue
    method = message.get("method")
    if method == "initialize":
        time.sleep(float(os.environ.get("STUB_DELAY") or 0))
        result = {"protocolVersion": message["params"].get("protocolVersion"), "capabilities": {"tools": {}},
                  "serverInfo": {"name": "t3", "version": "0"}}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        result = {"content": [{"type": "text", "text": message["params"]["name"] + " ok"}]}
    else:
        result = {}
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": result}) + "\n")
    sys.stdout.flush()
'''


# A stand-in pi in RPC mode: each prompt answers "done: <text>" after a bash call; "long" runs until abort.
STANDIN = r'''
import json, os, sys, threading, time
mode = os.environ.get("STANDIN_MODE")
lock, waiting, aborted = threading.Lock(), {}, threading.Event()
def emit(record):
    with lock:
        sys.stdout.write(json.dumps(record) + "\n"); sys.stdout.flush()
def update(event, **fields):
    emit({"type": "message_update", "assistantMessageEvent": {"type": event, **fields}})
def say(text, error=None):
    update("text_start", contentIndex=0); update("text_delta", contentIndex=0, delta=text)
    update("text_end", contentIndex=0, content=text)
    emit({"type": "message_end", "message": {"role": "assistant", "content": [{"type": "text", "text": text}],
          "stopReason": "error" if error else "stop", "errorMessage": error}})
def run(command, steers):
    emit({"type": "agent_start"})
    text = command["message"]
    if text == "Setup":
        if mode == "broken":
            say("", "No API key for provider server-pc")
        else:
            emit({"type": "extension_ui_request", "id": "n1", "method": "notify",
                  "message": "MCP servers need attention:\n  t3: needs sign-in, run /mcp login t3 (deferred)\nRun /mcp to fix."})
            say("ready")
    elif text == "long":
        aborted.wait(5); say("")
    elif text == "later":
        emit({"type": "extension_ui_request", "id": "q1", "method": "confirm", "title": "Allow rm?", "message": "rm x"})
        while "q1" not in waiting: time.sleep(0.05)
        say("confirmed: %s" % waiting["q1"].get("confirmed"))
    else:
        update("toolcall_start", contentIndex=0, id="c1", toolName="bash")
        update("toolcall_end", contentIndex=0, toolCall={"type": "toolCall", "id": "c1", "name": "bash", "arguments": {"command": "ls"}})
        emit({"type": "tool_execution_start", "toolCallId": "c1", "toolName": "bash", "args": {"command": "ls"}})
        emit({"type": "tool_execution_end", "toolCallId": "c1", "toolName": "bash", "isError": False,
              "result": {"content": [{"type": "text", "text": "a b"}]}})
        time.sleep(0.5)
        say("done: " + "+".join([text] + [s["message"] for s in steers]))
    emit({"type": "agent_end", "messages": []})
    emit({"type": "agent_settled", "aborted": aborted.is_set()})
busy, steers = None, []
for line in sys.stdin:
    command = json.loads(line)
    kind = command.get("type")
    if kind == "prompt":
        if command.get("streamingBehavior") == "steer":
            steers.append(command)
        elif busy and busy.is_alive():
            emit({"id": command.get("id"), "type": "response", "command": "prompt", "success": False, "error": "busy"})
            continue
        else:
            aborted.clear()
            busy = threading.Thread(target=run, args=(command, steers)); busy.start()
        emit({"id": command.get("id"), "type": "response", "command": "prompt", "success": True,
              "data": {"disposition": "queued" if command.get("streamingBehavior") else "started"}})
    elif kind == "abort":
        aborted.set()
    elif kind == "extension_ui_response":
        waiting[command["id"]] = command
if busy:
    busy.join()
'''


if __name__ == "__main__" and sys.argv[1:2] == ["--check-pi"]:
    check()
