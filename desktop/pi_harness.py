"""Rook's main agent on Pi (`pi`), through its RPC mode (`pi --mode rpc`).

RPC mode is JSONL on stdio: commands go in, and responses and session events come out. This harness turns Pi's
events into the Claude Code stream-json shapes that harness.py lists, so Rook's reader, watcher and cards keep their
code.

Nothing of the conversation stays on disk: Pi runs with --no-session, and screenshots travel inline.
Pi has no flag for tool servers, so pi_extension.ts registers Rook's. Their tools keep Claude Code's names,
mcp__<server>__<tool>, and load on first use through Pi's tool_search, as under Claude Code. Denied tools are hidden.

Pi has no permission modes: it runs every tool without asking (Pi's docs/security.md). So Rook maps no mode and adds
no layer. The person's own Pi extensions still load, as Claude Code keeps the person's hooks, so their own
permission gates still ask. Each such ask (an extension's confirm or select dialog) becomes a Rook card.

Self-check: ~/.local/share/rook/venv/bin/python desktop/pi_harness.py --check-pi
"""
import base64
import json
import os
from pathlib import Path
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
         "ls": "LS", "tool_search": "ToolSearch"}  # Pi's own tools by Claude Code's names. MCP names match already.
SKILLS = [
    ("delegate/SKILL.md", "find one with ToolSearch, such as `select:mcp__t3__t3_thread_list`.",
     "find one with tool_search, such as the query `mcp__t3__t3_thread_list`."),
    ("delegate/SKILL.md", "when ToolSearch cannot find the tools", "when tool_search cannot find the tools"),
    ("delegate/references/t3-command.md", "when ToolSearch cannot find the T3 tools",
     "when tool_search cannot find the T3 tools"),
    ("delegate/references/t3-tools.md", "Rook's Claude session", "Rook's Pi session"),
    ("wow/SKILL.md", "Find one that is not loaded yet with ToolSearch.", "Find one that is not loaded yet with tool_search."),
]
PROMPT = [("a full Claude Code session", "a full Pi session")]
CLAUDE_ONLY = ("${CLAUDE_", "ToolSearch")
NEEDS_ATTENTION = "MCP servers need attention:"  # Pi's one notice after startup about servers that failed.


def agent_dir():
    return Path(os.environ.get("PI_CODING_AGENT_DIR") or Path.home() / ".pi/agent")


def default_model():
    """The model Pi starts with when Rook names none, from Pi's own settings, or None."""
    try:
        model = json.loads((agent_dir() / "settings.json").read_text()).get("defaultModel")
    except (OSError, ValueError, AttributeError):
        return None
    return model if isinstance(model, str) and model else None


def stream(kind, **fields):
    return {"type": "stream_event", "parent_tool_use_id": None, "event": {"type": kind, **fields}}


def pi_servers(servers, denied):
    """Rook's servers as Pi's mcpServers entries: every tool loads on first use, and denied tools stay hidden."""
    hidden = {"t3": denied, **{spec["name"]: spec["denied_tools"] for spec in plugin_loader.servers()}}
    return {name: {**config, "exposure": "deferred", "toolExposure": {tool: "hidden" for tool in hidden.get(name, ())}}
            for name, config in servers.items()}


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
        prompt = codex_harness.edit(prompt, PROMPT, "Rook's system prompt")  # Rendered already in rook.py.
        return ["env", f"ROOK_PI_SERVERS={json.dumps(pi_servers(servers, denied))}", f"BROWSER={desk.false_exe()}",
                "pi", "--mode", "rpc", "--no-session", "--no-skills",
                *(arg for folder in folders for arg in ("--skill", str(folder))), "-e", str(EXTENSION),
                *(["--model", self.chosen] if self.chosen else []), *(["--thinking", self.effort] if self.effort else []),
                "--append-system-prompt", prompt]

    def setup(self, start, later, wow):
        """Claude Code's setup turn, with Pi's tool_search in place of ToolSearch."""
        names = [f"mcp__{server}__{tool}" for server, tools in start.items() for tool in tools]
        return settings.render(
            f"Setup, not a request from {OWNER}: "
            + (f"call tool_search with the query \"{' '.join(names)}\" and limit {len(names)}, " if names else "")
            + ("load the wow skill, " if wow and _has_skill("wow") else "") + "then reply ready."
            + (f" Find these with tool_search when you first need one: {'; '.join(later)}." if later else "")
            + " When a tool you used before is missing, search for it again.")

    def begin(self, process, session, uuid, text):
        """Send the setup turn, with the lines of the owner's session start hook, run in Pi's own folder, as Claude
        Code's hook adds them to its session. The hook takes about 20 ms."""
        cwd = os.readlink(f"/proc/{process.pid}/cwd") if Path(f"/proc/{process.pid}").is_dir() else os.getcwd()
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
                yield stream("content_block_start", content_block={
                    "type": "tool_use", "id": update.get("id"), "name": NAMES.get(update.get("toolName"), update.get("toolName"))})
            elif step == "toolcall_end":
                call = update.get("toolCall") or {}
                name, args = NAMES.get(call.get("name"), call.get("name")), call.get("arguments") or {}
                if name == "Bash":
                    args = {**args, "run_in_background": False}
                yield {"type": "assistant", "parent_tool_use_id": None, "message": {"role": "assistant", "content": [
                    {"type": "tool_use", "id": call.get("id"), "name": name, "input": args}]}}
        elif kind == "message_end" and (event.get("message") or {}).get("role") == "assistant":
            message = event["message"]
            yield from self.close_text()
            self.answer = "".join(block.get("text", "") for block in message.get("content") or ()
                                  if isinstance(block, dict) and block.get("type") == "text")
            self.error = (message.get("errorMessage") or "Pi's model failed.") if message.get("stopReason") == "error" else None
        elif kind == "tool_execution_end":
            content = [{"type": "text", "text": block["text"]} for block in (event.get("result") or {}).get("content") or ()
                       if isinstance(block, dict) and isinstance(block.get("text"), str)]
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
    """The harness against a stand-in pi that speaks RPC mode. No model, window or sound."""
    import asyncio
    import harness
    import tempfile

    # 1. Skills, prompt and setup text: no Claude-only words, and Rook's tables still match.
    with tempfile.TemporaryDirectory(prefix="rook-pi-check-") as tmp:
        base = Path(tmp)
        codex_harness.AGENTS = base / "no-agents"  # No session start hook: the owner's real one stays out.
        folders = skill_dirs(base / "skills", wow=True)
        assert folders[0] == base / "skills" and (base / "skills/delegate/SKILL.md").is_file()
        assert "tool_search" in (base / "skills/delegate/SKILL.md").read_text()
        codex_harness.edit((codex_harness.ROOT / "desktop/rook.py").read_text(), PROMPT, "desktop/rook.py")
        text = Pi().setup({"t3": ("t3_thread_send", "t3_thread_read")}, ["the other T3 tools"], False)
        assert '"mcp__t3__t3_thread_send mcp__t3__t3_thread_read" and limit 2' in text and "ToolSearch" not in text
        servers = pi_servers({"t3": {"type": "http", "url": "http://127.0.0.1:1/mcp"}, "render": {"command": "uv"}},
                             ("t3_project_delete",))
        assert servers["t3"] == {"type": "http", "url": "http://127.0.0.1:1/mcp", "exposure": "deferred",
                                 "toolExposure": {"t3_project_delete": "hidden"}}, servers
        assert servers["render"]["toolExposure"] == {}

        # 2. pick() and the argv, with a stand-in pi on PATH and Pi's settings in a scratch folder.
        (base / "bin").mkdir()
        standin = base / "bin/pi"
        standin.write_text(f"#!{sys.executable}\n" + STANDIN)
        standin.chmod(0o755)
        os.environ["PATH"] = f"{base / 'bin'}:{os.environ['PATH']}"
        os.environ["PI_CODING_AGENT_DIR"] = str(base / "agent")
        (base / "agent").mkdir()
        (base / "agent/settings.json").write_text('{"defaultModel": "llamacpp"}')
        chosen, problem = harness.pick({"agent": "pi"})
        assert type(chosen).__name__ == "Pi" and problem is None and chosen.model == "llamacpp", (chosen, problem)
        argv = chosen.command("You run as a full Claude Code session. Your memory is the agent memory folder that "
                              "your session start message names.", {"render": {"command": "uv"}}, "s", None, ())
        assert argv[argv.index("pi"):argv.index("pi") + 5] == ["pi", "--mode", "rpc", "--no-session", "--no-skills"]
        assert "--model" not in argv and "--thinking" not in argv and "a full Pi session" in argv[-1]
        # The prompt comes rendered from rook.py, where the person's notes pass as they are: no second render here.
        argv = chosen.command("a full Claude Code session. Notes: ⟦owner⟧ likes tea.", {}, "s", None, ())
        assert argv[-1] == "a full Pi session. Notes: ⟦owner⟧ likes tea.", argv[-1]
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
    print("all checks passed")


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
