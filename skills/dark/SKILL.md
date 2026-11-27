---
name: dark
description: "Turn Rook dark, as if ⟦owner⟧ turned it off for a while, and bring it back online. While dark, the swarm is gone, Rook takes no screenshots, and every message waits until Rook comes back. Use when ⟦owner⟧ asks Rook to go dark or quiet, to stay dark longer, or to come back online, such as \"go dark for an hour\", \"go quiet until three\", \"stay dark for another hour\", \"come back online\", \"you can come back\" or \"are you dark\"."
allowed-tools: Bash(/usr/bin/python ${CLAUDE_SKILL_DIR}/../../desktop/relay.py dark *)
---

# Going dark

The relay script is `${CLAUDE_SKILL_DIR}/../../desktop/relay.py`. Run it with `/usr/bin/python`.

| ⟦Owner⟧ says | Run |
|---|---|
| "go dark" | `relay.py dark on` |
| "go dark for an hour" | `relay.py dark on --for 1h` |
| "go quiet until three" | `relay.py dark on --until 15:00` |
| "stay dark" | nothing |
| "stay dark for another hour", "until four" | `relay.py dark on --for 1h` or `--until 16:00`. It replaces the end time. |
| "come back online", "you can come back" | `relay.py dark off`. It also cancels the end time. |
| "are you dark", "how long are you dark" | `relay.py dark status` |

Durations are written as for timers: 30m, 1h, 1h30m, up to 24h. A clock time is 12-hour with am or pm, such as 3 pm or 3:30 pm, or 24-hour, such as 15:30.

## Saying it

- Going dark: say one short line first, such as "Going dark for thirty minutes." or "Going dark until you need me." Then run the command and end the turn. Write nothing more: never confirm, and never describe the tools.
- If ⟦owner⟧ also asks for something else, do that first, and put its answer in that line, such as "Your meeting is at three. Going dark for an hour."
- If ⟦owner⟧ repeats ⟦himself⟧ before you finish, say no second line.
- Staying dark longer: the same, with the new end in the line.
- Coming back: one short sentence, such as "I'm back." The held messages reach you next, in one turn, and you sum them up then.

## While dark

- The swarm is gone. It shows only while you answer ⟦owner⟧, then goes away again.
- You see no screenshot. A request says so, so never guess at the screen.
- Thread messages, watcher news, status notes, and media from threads all wait until dark ends.
- ⟦Owner⟧'s plain timers still speak, and ⟦his⟧ task timers still run as turns.
- A question from ⟦owner⟧, or a task timer, gets an answer to that alone. Its request carries a line that says you are dark. Mention nothing that waits, and stay dark unless ⟦owner⟧ says to come back.
- Before ⟦verb:he goes|they go⟧ dark, ⟦owner⟧ can ask you to cancel ⟦his⟧ timers: `relay.py timer cancel all`.

## Coming back

When dark ends, by ⟦owner⟧ or by its end time, a turn says you are back and lists what came in while you were dark. Give one summary: first what needs ⟦owner⟧, then the updates. Leave out what is already settled. When nothing came in, say in a few words that you are back.
