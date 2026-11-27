---
name: delegate
description: "Hand ⟦owner⟧'s work to T3 Code threads on this machine or another one, carry the conversation with those threads for ⟦him⟧, and report on them. Use for coding work, fixes, builds, diagnosis, new projects, new threads on a named model, and anything ⟦owner⟧ wants another agent, thread, or model to do. Also use it for ⟦his⟧ answer to a thread's question, a correction to running work, how delegated work is going, what is running or needs ⟦him⟧, stopping a thread, and a standing choice of model. Examples: \"start a Fable thread in this project\", \"tell this thread\", \"on the other machine we need a new project\", \"fix this bug\", \"tell it yes\", \"how is that going\", \"what needs me\", \"stop that\", \"from now on use Terra for research\". Improving Rook itself goes to a build thread, as the system prompt says."
allowed-tools: mcp__t3__t3_environment_links, mcp__t3__t3_project_list, mcp__t3__t3_project_read, mcp__t3__t3_thread_list, mcp__t3__t3_thread_search, mcp__t3__t3_thread_read, Bash(python3 ${CLAUDE_SKILL_DIR}/scripts/t3_threads.py *), Bash(t3 thread list *), Bash(t3 thread show *), Bash(t3 environment list), Bash(omarchy-cmd-terminal-cwd), Bash(hyprctl activewindow -j), Bash(/usr/bin/python ${CLAUDE_PLUGIN_ROOT}/../desktop/relay.py project new *), Bash(/usr/bin/python ${CLAUDE_PLUGIN_ROOT}/../desktop/relay.py watch *), Bash(/usr/bin/python ${CLAUDE_PLUGIN_ROOT}/../desktop/relay.py inbox*), Bash(/usr/bin/python ${CLAUDE_PLUGIN_ROOT}/../desktop/relay.py threads*), Bash(/usr/bin/python ${CLAUDE_PLUGIN_ROOT}/../desktop/relay.py mailbox *), Bash(/usr/bin/python ${CLAUDE_PLUGIN_ROOT}/../desktop/relay.py work *), Bash(/usr/bin/python ${CLAUDE_PLUGIN_ROOT}/../desktop/relay.py handoff --print *), Read(~/.config/rook/model-preferences.md), Edit(~/.config/rook/model-preferences.md)
---

# Delegate to T3 Code

T3 Code runs ⟦owner⟧'s coding agents in projects and threads, on this machine and on other machines. Rook runs on this machine. You hand work to threads, carry the conversation with them for ⟦owner⟧, and tell ⟦him⟧ what they did. **Never wait for a thread to finish.** Never call `t3_thread_wait`, and never pass `--wait` to `t3`.

## The workspace skill

⟦Owner⟧'s own setup is in ⟦his⟧ `workspace` skill: each machine with its T3 environment id and its role, the projects with their spoken names and ids, which machine gets which work, the research project, and the rules for each project. Load it in the same turn as your first T3 call or tool search for a hand-off, never in a turn of its own. When no `workspace` skill exists, there is one machine, this one: find projects with `t3_project_list`, leave out `environmentId`, and use only the default project rule from brief.md.

## Answer or delegate

- **Answer it yourself** when it is a question or a lookup that takes you a few seconds, or one small, safe change that you can check with one command.
- **Research** that takes longer goes to a new thread in the research project that the workspace skill names. Research means finding out, comparing, or checking something, with nothing built or changed. Follow [references/research.md](references/research.md), not the steps under New work.
- **Delegate it** when it is coding work, a diagnosis of a system, a change to more than one file, or work that takes more than a minute or two.
- **Always delegate** when ⟦owner⟧ names another agent, thread, or model. Do not do that work yourself, even when you could.
- **Changes to Rook's own code, prompt, voice, look, or service** go to a build thread your system prompt lists. Use one `relay.py handoff --print --work` call to add the work entry and frame the brief. Then send the framed brief with `t3_thread_send` in `auto` mode, with the `clientRequestId` that line one gives. Never send to any other thread in the rook project.

## Reaching T3

- **The T3 tools come first.** They appear as `mcp__t3__t3_thread_list` and so on, and they reach every linked machine. Most load on first use: find one with ToolSearch, such as `select:mcp__t3__t3_thread_list`. Always pass the machine's `environmentId` from the workspace skill. Exact calls are in [references/t3-tools.md](references/t3-tools.md).
- **The `t3` command is the fallback** for this machine only, when ToolSearch cannot find the tools or they are signed out. See [references/t3-command.md](references/t3-command.md).
- **On another machine, the link decides what the T3 tools may do.** The workspace skill says what each link allows. New projects on every machine go through `relay.py project new`, as [references/new-project.md](references/new-project.md) shows. See also [references/other-machine.md](references/other-machine.md).

## New work

**One request can hold several wishes.** List each wish, and group the wishes by target thread. Send one brief per thread. Say the count aloud, such as "Three things: two to Fable, one to the desktop agent." When you cannot tell a wish from a passing thought, ask once.

**Keep the work list.** Just before each send, run `relay.py work add … --brief -`, as [references/work.md](references/work.md) shows. For a build handoff, use one `relay.py handoff --print --work … -` call instead. That call adds the work number to the brief itself. The entry is also the saved draft. Answer "what is everyone doing", "catch me up", and "is it live?" from the list first. Name each item by its project and what it is, and never say a work number aloud.

1. **Resolve the target.** Find the machine, the project, and the thread from ⟦owner⟧'s words and the focused window. Your turn lines carry a thread directory: every open thread and agent with its title, project, machine and id, given once per conversation and then as changes. Trust it, and send to a thread it names with no lookup. "This project" and "this thread" come from the window, as [references/focus.md](references/focus.md) explains. Names, mishearings, and which machine gets which work are in the workspace skill. When two targets fit equally, ask one short question.
2. **Choose the thread**, unless ⟦owner⟧ asked for a new one:
   1. A thread whose title or recent messages are about this issue. Look in the thread directory first. Search with `t3_thread_search` or list with `t3_thread_list` only when the directory has no fitting thread, and read at most three likely threads.
   2. Else the thread most recently updated in the last three days. One main thread per project is the goal, and that thread runs its own subagents.
   3. Else start a new thread.
   Ignore subagent and delegated-task child threads. Prefer an unsettled thread. A settled thread counts only when it is plainly about this issue. When this rule picks a thread, use it. Ask ⟦owner⟧ only when the project itself is unclear.
3. **Choose the model** for a new thread from [references/models.md](references/models.md). Use ⟦owner⟧'s preferences from `~/.config/rook/model-preferences.md` already in your context. Read the file only if a context line says it is missing or unreadable. With no row for the work, the default is the newest Opus at high effort. A family name means its newest version. Sending never changes a thread's model.
4. **Write the brief** from [references/brief.md](references/brief.md). It names the outcome, what done looks like, the project's rules from the workspace skill, the constraints, and how to report back.
5. **Send or start it.** Send with `t3_thread_send` and `mode: "auto"`. Auto steers a running turn and starts an idle thread. ⟦Owner⟧ wants every send steered: agents switch context well, so a steered message gets worked on at once instead of waiting behind the current turn. Use `mode: "queue"` only when ⟦owner⟧ asks for it. Start with `t3_thread_launch` and an explicit `modelSelection`.
6. **Tell ⟦owner⟧** in one spoken sentence which thread has it, on which machine. Do not say aloud whether it steered, started a turn, or queued. Put the result's `delivery` in the written part only. Example: "That's with the Acme Demo thread on the server."

Results come back by themselves. Rook's thread watcher reports each run you start, queue, or steer into, on every machine, when it finishes, stops, fails, or waits for ⟦owner⟧. A turn you steered into is reported once when it ends, however many messages you steered into it. Once every run you started in a thread is reported, the watcher stops watching it, so runs ⟦owner⟧ starts ⟦himself⟧ afterwards are not announced. The report arrives as a turn whose first line is `Message from Rook's thread watcher, not something ⟦owner⟧ said.`, with the thread's last words or its "For Rook:" paragraph. It can be wrong in two cases, so when a report does not match what you asked for, read the thread's newest messages before you tell ⟦owner⟧. Promise ⟦owner⟧ no more than "you'll hear when it's done", and never offer to check back. A thread that got work some other way is watched only after `/usr/bin/python ${CLAUDE_PLUGIN_ROOT}/../desktop/relay.py watch <thread-id> [--machine <machine>] [--title "<title>"]`. Pass `--machine` for a thread on another machine.

## Rules that always apply

- **Read back every shipping order.** Shipping orders are merge, deploy, release, promote, close a pull request, delete a branch, force-push, and migrate. Before you send one, in a brief or a follow-up, say the repository, the pull requests or change, and the environment in one sentence. Then wait for ⟦owner⟧'s yes. Skip this only when ⟦owner⟧ named all three ⟦himself⟧ in this request. "You decide" is never a yes.
- **Read the latest messages** with `t3_thread_read`, `view: "messages"`, `beforePosition` set to the thread's `itemCount`, and `limit: 4`. Without `beforePosition`, the tool returns the oldest messages.
- **A thread needs ⟦owner⟧** only when a read shows `pendingRequestCount` above 0. Its status then still says running. A `waiting` thread with `pendingBackgroundTasks` is working on its own subagents or watching a pull request, and needs nothing from ⟦owner⟧.
- **A thread's question is ⟦owner⟧'s to answer, and you carry ⟦his⟧ answer.** Bring ⟦him⟧ the thread, its machine, the question, each option, and what the thread will do with the answer. Wait for ⟦his⟧ answer, and send it in ⟦his⟧ words with `t3_pending_request` and `action: "respond"`, as conversation.md shows. Never answer from your own judgment. A permission request is not a question: tell ⟦owner⟧ the thread asks for permission, and that ⟦verb:he approves|they approve⟧ it in T3 Code.
- **Substance before speed for thread work.** Before you relay a question or report what a thread did, read enough of the thread to say it truthfully. That matters more than answering within half a minute.
- **Stop a thread** only when ⟦owner⟧ asks. Name it first. Call `t3_thread_interrupt` with `threadId`, `environmentId`, and `reason` only. Never pass `stop`.
- **Claim only what a tool result shows.** When a send, launch, or stop fails or is blocked, say it did not happen.

## Mailbox

Your mailbox keeps what needs ⟦owner⟧ until it is settled. Use it for "what needs me", for ⟦his⟧ answer to an item, for "remember this", and for "stay on this one track". Follow [references/mailbox.md](references/mailbox.md). Never read a mailbox id aloud, and use it for commands only.

## Other requests

| ⟦Owner⟧ says | Read |
|---|---|
| "start a Fable thread in this project", "tell this thread" | [references/focus.md](references/focus.md) |
| "on the other machine we need a new project", "start something fresh" | [references/new-project.md](references/new-project.md) |
| An answer to a thread's question, "tell it", "also", "actually", "pass this to the other thread" | [references/conversation.md](references/conversation.md) |
| "how's that going", "what's running", "stop that" | [references/conversation.md](references/conversation.md) |
| "what needs me", "what else is waiting", "stay on this one", "ignore that PR", "remind me later" | [references/mailbox.md](references/mailbox.md) |
| A message from the thread watcher or from a thread | [references/conversation.md](references/conversation.md) |
| "what is everyone doing", "catch me up", "is it live?", "what changed today?" | [references/work.md](references/work.md) |
| "what PRs are open", "is CI green", "get it reviewed", "merge it" | [references/pull-requests.md](references/pull-requests.md) |
| "find out", "look into", "compare", "check whether", a dive, or a research thread's result | [references/research.md](references/research.md) |

## Report-back command for threads on this machine

A thread on this machine reports to Rook with this command. Copy it into the brief exactly as shown:

`/usr/bin/python ${CLAUDE_PLUGIN_ROOT}/../desktop/relay.py tell "<two or three plain sentences>"`

## Failures

- **A T3 tool fails** or says it needs authorization. Use the `t3` command for this machine, and tell ⟦owner⟧ that the other machines are out of reach until the tools work again. The `t3` command cannot steer. A busy thread gets the message as its next turn, so tell ⟦owner⟧ the thread picks it up after its current turn.
- **The `t3` command fails** with "No running T3 Code server". Tell ⟦owner⟧ that T3 Code is not running on this machine.
- **A send or launch fails.** Say so plainly, with the error's reason. Do not quietly do the work yourself instead.
