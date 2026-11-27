---
name: about
description: "How Rook works inside and where each part of Rook is kept: how its prompt is built, its code, settings and state folders, skills and plugins, voices, the overlay, the thread watcher, mailbox, work list, timers and build threads. Use when ⟦owner⟧ asks a question about how Rook works or where something of Rook's is kept, such as \"how do you work\", \"where do you keep my timers\", \"how is your prompt built\", \"what happens when I talk to you\" or \"where do my skills go\". A request to change Rook goes to a build thread without this skill, and the rook:settings skill changes settings."
---

# How Rook works

Read this before you search Rook's code. Each part names the file that holds it. Read that file before you claim how it behaves. Rook's code is the folder two levels above this skill, `${CLAUDE_SKILL_DIR}/../..`.

## What Rook is

Rook is one Python session, the `Companion` class in `desktop/rook.py`. It drives one coding agent at a time, and that agent is you. One of Rook's settings picks Claude Code, Antigravity, Codex or Pi, through `desktop/harness.py`, `desktop/agy_harness.py`, `desktop/codex_harness.py` or `desktop/pi_harness.py`. When the chosen agent cannot start, `Companion.fall_back` starts Claude Code, and the startup turn says why.

## How your prompt is built

`Companion.launch_agent` in `desktop/rook.py` builds your system prompt at each start. It holds your identity, House Style from `prompts/house-style.md` with ⟦owner⟧'s personality notes woven in, ⟦his⟧ routing and model preferences, and then fixed paragraphs. Active plugins fill the slots in `PROMPT_SLOTS` through `desktop/plugin_loader.py`. Each agent's harness rewrites a few sentences from a table, such as the name of the session. The setup turn, from `Harness.setup` in `desktop/harness.py`, loads the first tools and carries the recent conversation as text. Every start is a fresh session, so a change to the prompt, a skill or a plugin takes effect at the next start.

## Where things live

- **Code.** `desktop/` holds Rook itself, `skills/` the built-in skills, `plugins/` the bundled plugins, and `prompts/` and `themes/` the rest. An installed Rook runs from `~/.local/share/rook/live`.
- **Settings**, in `~/.config/rook/`: `settings.json`, `personality.md`, `model-preferences.md` and `machines.json`, with the folders `skills/`, `plugins/` and `themes/`.
- **State**, in `~/.local/state/rook/`: `turns.jsonl` is the turn log. `mailbox.db` holds the mailbox, the request journal and the timers. `work.json`, `dark.json`, `watching.json` and `presence.json` hold the work list, dark mode, the watched threads and presence.
- **Data**, in `~/.local/share/rook/`: `memory/` is Rook's own memory folder. With shared agent memory, the session start lines name the folder instead. Your system prompt says which one you use.
- **Runtime folder.** `rook.sock` is Rook's inbox. Each agent gets a private home there, such as `rook-claude` or `rook-antigravity`.

The folders follow the XDG variables when they are set.

## Skills and plugins

Built-in skills live in `skills/`. Claude Code lists them as `rook:<name>`, and Antigravity, Codex and Pi list them by bare name. ⟦Owner⟧'s own skills live in `~/.config/rook/skills`, and the rook:extend skill adds one. A bundled plugin turns on by its own rule. A plugin in `~/.config/rook/plugins` stays off until `settings.json` turns it on. `relay.py plugin list` says which plugins are on and why.

## What runs while ⟦owner⟧ talks

- **Hearing.** AirType's Parakeet speech recognition runs inside `desktop/rook.py`.
- **Voice.** `desktop/speech.py` keeps the small voice loaded on this computer. The medium voice comes from a voice server at the address in the settings, with the small voice as its fallback. `desktop/medium_voice.py` can run that server on this computer.
- **Overlay.** `desktop/overlay.py` draws the swarm of gold dust, the captions, the media viewer and the scenes. `desktop/render.py` checks each scene, and `desktop/render_tool.py` is your show_scene tool.
- **Thread watcher.** `desktop/watch.py` polls the threads you handed work to about once a minute. It tells you through the inbox when one finishes, stops or needs ⟦owner⟧.
- **Inbox.** A thread runs `relay.py tell`, which reaches you through `rook.sock`.
- **Mailbox.** `desktop/mailbox.py` keeps what needs ⟦owner⟧ until it is settled.
- **Work list.** `desktop/work.py` keeps each wish handed to a thread, through `relay.py work`.
- **Timers and dark mode.** `relay.py timer` and `relay.py dark` reach the running `Companion` in `desktop/rook.py`, which keeps both.
- **Phone app.** `desktop/server.py` serves it, and `desktop/session.py` is its session.
- **Memory.** In Rook's own memory, `relay.py remember` saves a fact at once, and `desktop/memory.py` folds the facts into notes each night. With shared agent memory, `relay.py remember` refuses and names the command to use instead.

## Changing things

Settings, such as the voice, its speed or the main agent, belong to the rook:settings skill. New skills belong to the rook:extend skill. Anything else, such as Rook's code, prompt or look, goes to a build thread, as your system prompt says. Never edit or restart yourself.

## Look closer

- `/usr/bin/python ${CLAUDE_SKILL_DIR}/../../desktop/relay.py --help` lists every command.
- `relay.py get` prints each setting and where its value comes from.
