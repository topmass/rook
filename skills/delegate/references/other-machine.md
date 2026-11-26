# Other machines

⟦Owner⟧ runs T3 Code on this machine and controls ⟦his⟧ agents on other machines from there. Rook does the same through the T3 tools. The workspace skill names each machine, its `environmentId`, its address, its role, what its link allows, and when the link expires.

## The link

- **A link's access caps every call through it.** The workspace skill says what each link allows, and what was tested there.
- **A link may not change projects.** Then creating, registering, or deleting a project there through the T3 tools returns `capability_denied`, and a thread Rook starts there inherits the same limit. `relay.py project new` creates projects there instead, as new-project.md shows.
- **A thread Rook starts there runs at the link's mode at most.** When the workspace skill gives a `runtimeMode` for the machine, pass it to `t3_thread_launch`. In `auto` mode the agent's reviewer checks risky actions, and the agent may stop to ask for approval. Such a thread then waits for ⟦owner⟧ in T3 Code. Say so when it happens.
- **Threads ⟦owner⟧ started there** keep their own mode, often `full-access`. Sending to them does not change it.
- **The `t3` command cannot reach another machine.** Only the T3 tools can, with the `environmentId`.

## Expiry

`t3_environment_links` shows each link's `expiresAt`. In the week before that date, tell ⟦owner⟧ once in a session that the link to that machine runs out soon. When ⟦verb:he wants|they want⟧ it renewed, hand it to the build thread, as your system prompt says. Renewal needs a new pairing code from that machine, which only ⟦owner⟧ can make there.

## When another machine does not answer

Call `t3_environment_links`. Its `status` and `lastError` say why.

- **Unreachable or offline.** Say: "I can't reach <machine> right now, so I couldn't hand that over." Offer to start the work on this machine instead, and start nothing until ⟦owner⟧ says yes.
- **Expired.** Say that the link to that machine has expired and that the build thread can renew it. Hand that to the build thread only when ⟦owner⟧ agrees.
- **A tool error that names authorization.** The T3 tools are signed out. Say that you need to be signed in to T3 again, and fall back to the `t3` command for this machine.

Never run `ssh` by hand to reach another machine. Only `relay.py project new` and the thread watcher use the machine table's connection there, each for its own job. Never link or unlink an environment yourself.

## Reporting back

A thread on another machine cannot run `relay.py tell`, because Rook's inbox is a socket on this machine. Its brief asks it to end its final message with a "For Rook:" paragraph instead, as brief.md shows. Rook's thread watcher reads threads on other machines over the machine table's SSH connection, takes that paragraph, and passes it on when the thread finishes. That connection serves two jobs only: the watcher's reads and `relay.py project new`. Rook never runs `ssh` by hand.
