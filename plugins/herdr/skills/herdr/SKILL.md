---
name: herdr
description: Hand ⟦owner⟧'s work to coding agents in Herdr, and report on them. Use it when ⟦owner⟧ uses Herdr or Pi, or names one: their agents, what they are doing, a send, a new agent, or a Pi session. Also use it for a hand-off that names no orchestrator when your system prompt says such hand-offs go to Herdr.
allowed-tools: Bash(/usr/bin/python ${CLAUDE_PLUGIN_ROOT}/../desktop/relay.py herdr agents*), Bash(/usr/bin/python ${CLAUDE_PLUGIN_ROOT}/../desktop/relay.py herdr read *), Bash(/usr/bin/python ${CLAUDE_PLUGIN_ROOT}/../desktop/relay.py pi *)
---

# Herdr and Pi

Herdr runs coding agents in terminal panes, on this machine and on saved Herdr machines. Pi is one of those agents. The command is `/usr/bin/python ${CLAUDE_PLUGIN_ROOT}/../desktop/relay.py`, shown below as `relay.py`. Each command is one call, and its output is short enough to speak from.

## Commands

- `relay.py herdr agents` lists every agent: name, kind, state, folder and machine.
- `relay.py herdr read AGENT [--machine NAME] [--lines N]` gives the agent's state and the end of its screen.
- `relay.py herdr send AGENT [--machine NAME] "<text>"` sends one message.
- `relay.py herdr start <folder> --kind claude|codex|pi|... [--model MODEL] [--name NAME] "<first prompt>"` opens a new Herdr workspace for the folder without focus, starts the agent there, and sends the first prompt. On a saved machine, give the folder as an absolute path or one that starts with `~/`.
- `relay.py pi sessions` and `relay.py pi read <session id>` read Pi's saved sessions. They never change them. A live Pi agent runs inside Herdr: start it with `--kind pi`.

Pass a long message on stdin with `-` and a quoted heredoc. Write a first prompt the way you write a brief for a thread.

## A hand-off

1. **Find the agent.** Run `relay.py herdr agents`. A done or idle agent in the work's folder takes it with `send`. Otherwise `start` a new one in that folder.
2. **Choose the kind** ⟦owner⟧ names, such as claude, codex, or pi. With none named, use claude. When ⟦verb:he names|they name⟧ a model, pass its id with `--model`, from the rook:delegate skill's models.md.
3. **Tell ⟦owner⟧** in one spoken sentence which agent has it, on which machine.

## States

- **working**: busy. A send waits until it is done.
- **blocked**: it waits at a question or an approval. Tell ⟦owner⟧ which agent needs ⟦him⟧, and that ⟦verb:he answers|they answer⟧ it in Herdr. Never send it keys, and never answer or approve anything for ⟦him⟧. Each agent keeps its own permission settings.
- **done** or **idle**: ready for a message.
- **unknown**: Herdr cannot tell. Read it before you say anything about it.

## Sends

- A send goes only to an agent that is done or idle. A refusal says why. Tell ⟦owner⟧ in one sentence, and do not try again by yourself.
- An unknown outcome means the message may or may not have arrived. Tell ⟦owner⟧ that, and that ⟦he⟧ can check the agent in Herdr. Never send it again unless ⟦verb:he asks|they ask⟧ after ⟦he⟧ checked.
- Rook watches each agent you send to or start, and says when it is blocked or done. Never wait for an agent.
