# The t3 command, the fallback

Use this only when ToolSearch cannot find the T3 tools or they are signed out. The `t3` command talks to this machine's T3 server and has no way to reach another machine. Its thread commands sign in for one command at a time with full access.

## Listing

- `python3 ${CLAUDE_SKILL_DIR}/scripts/t3_threads.py list <project>` prints the project's top-level threads from the last seven days, newest first. Projects are paths, or titles or aliases of this machine's rows in the workspace skill, such as `rook`. With no project, it lists every project the workspace skill gives for this machine.
- `t3_threads.py list --active` prints the threads that are working now.
- `t3_threads.py needs` prints unsettled threads from the last three days that wait for ⟦owner⟧, stopped, or finished.
- `t3_threads.py peek <id> <id>` prints the last three messages of each thread.

## Sending and starting

Pass the brief on stdin with a quoted heredoc, so nothing in it is expanded.

Always pass `--json`. Rook's thread watcher reads the run id and delivery from that JSON, so it watches the exact run.

- Existing thread: `t3 thread send <thread-id> - --json <<'BRIEF'`, then the brief, then `BRIEF`. The JSON's `delivery` says `queued` when the brief waits behind other work, or `started` when the thread was idle. When it was queued, tell ⟦owner⟧ the thread picks it up after its current turn.
- New thread: `t3 thread start <project-path> - --json --title "<three to six words>" --provider <p> --model <m> --option <id>=<value> <<'BRIEF'`. The JSON holds the new `threadId` and `runId`. Always pass the model. Without it, T3 starts the thread on its own default model, which may not be ⟦owner⟧'s default. Threads started this way run in full access.

## What it cannot do

- It cannot reach another machine.
- It cannot list projects. The workspace skill's projects stand in.
- It cannot steer. A busy thread gets the message as its next turn, never during the current one.
- It cannot stop a running turn. A sent message only waits behind the current turn. Tell ⟦owner⟧ to press stop in T3 Code.
